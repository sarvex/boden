import os, sys
import logging
import subprocess
import shutil
import re
import tempfile
from zipfile import ZipFile, ZipInfo

from buildexecutor import BuildExecutor
from androidstudioprojectgenerator import AndroidStudioProjectGenerator
from cmake import CMake
from gradle import Gradle
from gradle import download_file

import error

class MyZipFile(ZipFile):

    def extract(self, member, path=None, pwd=None):
        if not isinstance(member, ZipInfo):
            member = self.getinfo(member)

        if path is None:
            path = os.getcwd()

        ret_val = self._extract_member(member, path, pwd)
        attr = member.external_attr >> 16
        if attr != 0:
            os.chmod(ret_val, attr)
        return ret_val

    def extractall(self, path=None, members=None, pwd=None):
        if members is None:
            members = self.namelist()

        if path is None:
            path = os.getcwd()

        for zipinfo in members:
            self.extract(zipinfo, path, pwd)

class AndroidExecutor:
    def __init__(self, buildExecutor, generatorInfo, sourceDirectory, buildFolder, rootPath):
        self.logger = logging.getLogger(__name__)
        self.generatorInfo = generatorInfo
        self.sourceDirectory = sourceDirectory
        self.buildFolder = buildFolder
        self.buildExecutor = buildExecutor
        self.gradle = Gradle(sourceDirectory)
        self.rootPath = rootPath
        self.cmake = CMake()

        self.androidBuildApiVersion = "28"
        self.androidBuildToolsVersion = "28.0.2"
        self.androidEmulatorApiVersion = "28"

    def buildTarget(self, configuration, args, target):
        androidAbi = self.getAndroidABIFromArch(configuration.arch)
        androidHome = self.getAndroidHome()
        buildDir = self.buildFolder.getBuildDir(configuration)

        if configuration.buildsystem == "AndroidStudio":
            self.buildTargetAndroidStudio(configuration, args, target, androidAbi, androidHome, buildDir)
        else:
            self.buildTargetMake(configuration, args, target)

    def buildTargetMake(self, configuration, args, target):
        buildExecutor = BuildExecutor(self.generatorInfo, self.rootPath, self.sourceDirectory, self.buildFolder)
        buildExecutor.buildTarget(configuration, args, target)

    def buildTargetAndroidStudio(self, configuration, args, target, androidAbi, androidHome, buildDir):

        gradlePath = self.gradle.getGradlePath()
        gradleWrapperPath = self.getBuildToolPath(buildDir, "gradlew")

        arguments = ["\"" + gradleWrapperPath + "\""]

        if target == "clean":
            arguments += ["clean"]
        elif args.config=="Release":
            arguments += ["assembleRelease"]
        else:
            arguments += ["assembleDebug"]

        self.logger.debug("Starting: %s", arguments)

        exitCode = subprocess.call(" ".join(arguments), shell=True, cwd=buildDir, env=self.getToolEnv());
        if exitCode!=0:
            raise error.ToolFailedError(f"{arguments}", exitCode);

    def build(self, configuration, args):
        self.buildTarget(configuration, args, None)

    def clean(self, configuration, args):
        self.buildTarget(configuration, args, "clean")

    def package(self, configuration, args):
        if configuration.buildsystem == "AndroidStudio":
            self.logger.critical("Cannot build packages with Android Studio, use make instead")
        else:
            self.buildTarget(configuration, args, "package")

    def prepare(self, platformState, configuration, args):
        androidAbi = self.getAndroidABIFromArch(configuration.arch)
        androidHome = self.getAndroidHome()

        self.prepareAndroidEnvironment(configuration, args.accept_terms)

        buildDir = self.buildFolder.getBuildDir(configuration)

        if configuration.buildsystem == "AndroidStudio":
            self.prepareAndroidStudio(platformState, configuration, androidAbi, androidHome, buildDir, args)
        else:
            self.prepareMake(platformState, configuration, args, androidAbi, androidHome, buildDir)

    def prepareMake(self, platformState, configuration, args, androidAbi, androidHome, cmakeBuildDir):
        self.cmake.open(self.sourceDirectory, cmakeBuildDir, "Unix Makefiles")

        android_abi_arg = self.getAndroidABIFromArch(configuration.arch)
        if not android_abi_arg:
            raise error.InvalidArchitectureError("No target architecture specified. The architecture parameter is required for makefile build systems.")

        cmakeArguments = [
            f"-DCMAKE_TOOLCHAIN_FILE={androidHome}/ndk-bundle/build/cmake/android.toolchain.cmake",
            f"-DANDROID_ABI={android_abi_arg}",
            f"-DANDROID_NATIVE_API_LEVEL={self.androidBuildApiVersion}",
            f"-DCMAKE_BUILD_TYPE={configuration.config}",
            "-DBDN_BUILD_TESTS=Off",
            "-DBDN_BUILD_EXAMPLES=Off",
        ]

        if args.cmake_option:
            for option in args.cmake_option:
                cmakeArguments += [f"-D{option}"]


        if args.package_generator:
            cmakeArguments += [f"-DCPACK_GENERATOR={args.package_generator}"]

        if args.package_folder:
            packageFolder = args.package_folder
            if not os.path.isabs(packageFolder):
                packageFolder = os.path.join(self.buildFolder.getBaseBuildDir(), packageFolder)

            cmakeArguments += [f"-DCPACK_OUTPUT_FILE_PREFIX={packageFolder}"]


        self.logger.warning("Disabling examples and tests, as we cannot build apk's yet.")

        self.logger.debug("Starting configure ...")
        self.logger.debug(" Source Directory: %s", self.sourceDirectory)
        self.logger.debug(" Output Directory: %s", cmakeBuildDir)
        self.logger.debug(" Config: %s", configuration.config)
        self.logger.debug(" Arguments: %s", cmakeArguments)
        self.logger.debug(" Generator: %s", "Unix Makefiles")

        self.cmake.configure(cmakeArguments)

    def prepareAndroidStudio(self, platformState, configuration, androidAbi, androidHome, buildDir, args):
        gradlePath = self.gradle.getGradlePath()

        self.gradle.stop()

        tmpCMakeFolder = os.path.join(buildDir, "tmp-cmake-gen")

        makefile_android_abi = self.getAndroidABIFromArch(configuration.arch)
        if not makefile_android_abi:
            # If we target multiple architectures at the same time, we simply use x86 for the temporary
            # Makefile project we generate here (since makefiles support only one architecture).
            # Note that the makefile is only used temporarily to detect the available projects and is never
            # used to build anything.
            makefile_android_abi = "x86"

        self.cmake.open(self.sourceDirectory, tmpCMakeFolder, "Unix Makefiles")

        cmakeArguments = [
            f"-DCMAKE_TOOLCHAIN_FILE={androidHome}/ndk-bundle/build/cmake/android.toolchain.cmake",
            "-DCMAKE_SYSTEM_NAME=Android",
            f"-DANDROID_ABI={makefile_android_abi}",
            f"-DANDROID_NATIVE_API_LEVEL={self.androidBuildApiVersion}",
            "-DBAUER_RUN=Yes",
        ]

        if sys.platform == 'win32':
            cmakeArguments += [
                f"-DCMAKE_MAKE_PROGRAM={androidHome}/ndk-bundle/prebuilt/windows-x86_64/bin/make.exe"
            ]

        if args.cmake_option:
            for option in args.cmake_option:
                cmakeArguments += [f"-D{option}"]

        self.logger.debug("Starting configure ...")
        self.logger.debug(" Arguments: %s", cmakeArguments)
        self.logger.debug(" Generator: %s", "Unix Makefiles")

        self.cmake.configure(cmakeArguments)

        cmakeConfigurations = self.cmake.codeModel["configurations"]
        if len(cmakeConfigurations) != 1:
            raise Exception("Number of configurations is not 1!")

        target_dependencies = self.calculateDependencies(self.cmake.codeModel)

        config = cmakeConfigurations[0]
        project = config["main-project"]

        self.logger.debug("Found project: %s", project["name"])
        targetNames = []
        targets = []
        for target in project["targets"]:
            if target["type"] in [
                "SHARED_LIBRARY",
                "EXECUTABLE",
                "STATIC_LIBRARY",
            ]:
                self.logger.debug("Found target: %s", target["name"])
                targetNames += [target["name"]]
                targets += [target]

        project = {"name" : project["name"], "sourceDirectory" : project["sourceDirectory"],"targetNames" : targetNames, "targets" : targets}

        # Use external CMake for building native code (supported as of AndroidStudio 3.2)
        generator = AndroidStudioProjectGenerator(self.gradle, self.cmake, buildDir, self.androidBuildApiVersion)

        generator.generate(project, androidAbi, target_dependencies, args)

    def getToolEnv(self):
        toolEnv = os.environ
        toolEnv["ANDROID_HOME"] = self.getAndroidHome()
        return toolEnv

    def getAndroidHome(self):
        android_home_dir = os.environ.get("ANDROID_HOME")
        if not android_home_dir:
            if sys.platform.startswith("linux"):
                android_home_dir = os.path.expanduser("~/Android/Sdk")
                if os.path.exists(android_home_dir):
                    self.logger.info("Android home directory automatically detected as: %s", android_home_dir)
                else:
                    android_home_dir = None

            if sys.platform == "darwin":
                android_home_dir = os.path.expanduser("~/Library/Android/sdk")

                if os.path.exists(android_home_dir):
                    self.logger.info("Android home directory automatically detected as: %s", android_home_dir)
                else:
                    android_home_dir = None

            if sys.platform == "win32":
                android_home_dir = os.path.expanduser("~/AppData/Local/Android/SDK")

                if os.path.exists(android_home_dir):
                    self.logger.info("Android home directory automatically detected as: %s", android_home_dir)
                else:
                    android_home_dir = None

        if not android_home_dir:                    
            raise Exception("ANDROID_HOME environment variable is not set. Please point it to the root of the android SDK installation.")

        return android_home_dir.replace('\\', '/')

    def getAndroidABIFromArch(self, arch):
        return None if arch=="std" else arch

    def getAndroidABI(self, configuration):
        return self.getAndroidABIFromArch(configuration.arch)

    def getBuildToolPath(self, androidHome, tool):
        path = os.path.join(androidHome, tool)
        if sys.platform == "win32":
            if os.path.exists(f"{path}.bat"):
                path += ".bat"
            elif os.path.exists(f"{path}.exe"):
                path += ".exe"

        if not os.path.exists(path):
            raise Exception(f"Couldn't find {tool}")

        return path

    def calculateDependencies(self, codeModel):
        cmakeConfigurations = codeModel["configurations"]
        if len(cmakeConfigurations) != 1:
            raise Exception("Number of configurations is not 1!")

        config = cmakeConfigurations[0]
        projects = []
        artifacts = {}

        for project in config["projects"]:
            for target in project["targets"]:
                if "artifacts" in target and target["type"] == "SHARED_LIBRARY" or target["type"] == "STATIC_LIBRARY":
                    artifacts[target["name"]] = []
                    for artifact in target["artifacts"]:
                        artifacts[target["name"]] += [os.path.basename(artifact)]

        dependencies = {}

        for project in config["projects"]:
            for target in project["targets"]:
                dependencies[target["name"]] = []
                if "linkLibraries" in target:
                    for depname, artifactList in artifacts.items():
                        for artifact in artifactList:
                            if artifact in target["linkLibraries"]:
                              dependencies[target["name"]] += [ depname ]

        return dependencies

    def tryDetectAndroidCmakeComponentName(self, sdkManagerPath):

        command = f'"{sdkManagerPath}" --list'
        try:
            output = subprocess.check_output( command, shell=True, env=self.getToolEnv(), universal_newlines=True )
        except:
            self.logger.warning("Failed to get Android SDK module list")
            return None

        last_cmake_component_name = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("cmake;"):
                last_cmake_component_name = line.partition(" ")[0]
                break

        return last_cmake_component_name

    def workaroundPlatformTools2903(self):
        try:
            androidHome = self.getAndroidHome()
            sdkManagerPath = self.getBuildToolPath(androidHome, "tools/bin/sdkmanager")

            sdkManagerCommand = f'"{sdkManagerPath}" --list'
            output =  subprocess.check_output(sdkManagerCommand, shell=True, env=self.getToolEnv() )

            for line in output.splitlines():
                parts = line.decode('utf-8').split('|')
                if len(parts) == 3 and parts[0].strip() == 'platform-tools':
                    version = parts[1].strip()
                    if version == '29.0.3':
                        self.logger.info("Since platform-tools 29.0.3 breaks debugging native apps, we manually download 29.0.2")
                        tf = tempfile.NamedTemporaryFile(mode='w+b', delete=False)

                        sourceName = "https://dl.google.com/android/repository/platform-tools_r29.0.2-"
                        if "linux" in sys.platform :
                            sourceName += "linux"
                        elif sys.platform == "win32":
                            sourceName += "windows"
                        elif sys.platform == "darwin":
                            sourceName += "darwin"
                        sourceName += ".zip"

                        download_file(sourceName, tf.name)

                        zipf = MyZipFile(tf.name, 'r')
                        zipf.extractall(androidHome)
                        zipf.close()

                        return True
            return False
        except:
            return False

    def prepareAndroidEnvironment(self, configuration, accept_terms):
        self.logger.info("Preparing android environment...")
        androidAbi = self.getAndroidABIFromArch(configuration.arch)
        androidHome = self.getAndroidHome()
        sdkManagerPath = self.getBuildToolPath(androidHome, "tools/bin/sdkmanager")

        if accept_terms:
            self.logger.info("Ensuring that all android license agreements are accepted ...")

            licenseCall = subprocess.Popen(
                f'"{sdkManagerPath}" --licenses',
                shell=True,
                env=self.getToolEnv(),
                stdin=subprocess.PIPE,
            )

            licenseInputData = "".join("y\n" for _ in range(100))
            licenseCall.communicate(licenseInputData.encode('utf-8'))

            self.logger.info("Done updating licenses.")

        self.logger.info("Ensuring that all necessary android packages are installed...")

        platformToolsPackageName = '"platform-tools"'

        if self.workaroundPlatformTools2903():
            platformToolsPackageName = ""

        sdkManagerCommand = f'"{sdkManagerPath}" {platformToolsPackageName} "ndk-bundle" "extras;android;m2repository" "extras;google;m2repository" "build-tools;{self.androidBuildToolsVersion}" "platforms;android-{self.androidBuildApiVersion}"'

        if cmakeComponentName := self.tryDetectAndroidCmakeComponentName(
            sdkManagerPath
        ):
            sdkManagerCommand += f' "{cmakeComponentName}"'

        try:
            subprocess.check_call( sdkManagerCommand, shell=True, env=self.getToolEnv() )
        except:
            self.logger.warning("Failed getting emulator, you will not be able to 'run' this configuration")

        self.logger.info("Done updating packages.")
