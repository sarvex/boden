import logging
import os
import subprocess
import shutil

import error
from cmake import CMake
from compilerinfo import CompilerInfo


class BuildExecutor:
    def __init__(self, generatorInfo, rootDirectory, sourceDirectory, buildFolder):
        self.logger = logging.getLogger(__name__)
        self.cmake = CMake()
        self.generatorInfo = generatorInfo
        self.sourceDirectory = sourceDirectory
        self.rootDirectory = rootDirectory

        self.buildFolder = buildFolder

    def build(self, configuration, args):
        self.buildTarget(configuration, args, args.target)

    def clean(self, configuration, args):
        self.buildTarget(configuration, args, "clean")

    def package(self, configuration, args):
        self.buildTarget(configuration, args, "package")

    def buildTarget(self, configuration, args, target):
        configs = [configuration.config]

        if args.config != None:
            configs = [args.config]

        if target is None and args.target != None:
            target = args.target

        isSingleConfigBuildSystem = self.generatorInfo.isSingleConfigBuildSystem(configuration.buildsystem)

        if not isSingleConfigBuildSystem and args.config is None:
            configs = [
                cmakeConfiguration["name"]
                for cmakeConfiguration in self.cmake.codeModel["configurations"]
            ]
        for config in configs:
            buildDirectory = self.buildFolder.getBuildDir(configuration)
            commandArguments = ["\"%s\"" % self.cmake.cmakeExecutable, "--build", "\"%s\"" % buildDirectory]

            if target:
                commandArguments += ["--target", target];

            if not isSingleConfigBuildSystem:
                commandArguments += ["--config", config];

            if args.jobs != None:
                generatorName = self.generatorInfo.getCMakeGeneratorName(configuration.buildsystem);
                if "Visual Studio" in generatorName:
                    os.environ["CL"] = f"/MP{args.jobs}"
                elif "Xcode" not in generatorName:
                    commandArguments += ["--", f"-j{args.jobs}"]

            commandLine = " ".join(commandArguments)
            self.logger.info("Calling: %s", commandLine)

            exitCode = subprocess.call(commandLine, shell=True, cwd=buildDirectory);
            if exitCode!=0:
                raise error.ToolFailedError(commandLine, exitCode);


    def prepare(self, platformState, configuration, args):
        self.logger.debug("prepare(%s)", configuration)

        cmakeBuildDir = self.buildFolder.getBuildDir(configuration);

        toolChainFileName = None;
        needsCleanBuildDir = False
        cmakeEnvironment = "";
        cmakeArch = configuration.arch;
        cmakeArguments = [];

        self.generatorInfo.ensureHaveCmake()

        generatorName = self.generatorInfo.getCMakeGeneratorName(configuration.buildsystem);

        commandIsInQuote = False;

        if args.package_generator:
            cmakeArguments += [f"-DCPACK_GENERATOR={args.package_generator}"]

        if args.package_folder:
            packageFolder = args.package_folder
            if not os.path.isabs(packageFolder):
                packageFolder = os.path.join(self.buildFolder.getBaseBuildDir(), packageFolder)

            cmakeArguments += [f"-DCPACK_OUTPUT_FILE_PREFIX={packageFolder}"]

        if configuration.platform=="mac":
            if configuration.arch!="std":
                raise error.InvalidArchitectureError(arch);

            if args.macos_sdk_path:
                cmakeArguments.extend([f"-DCMAKE_OSX_SYSROOT={args.macos_sdk_path}"])
            if args.macos_min_version:
                cmakeArguments.extend(
                    [f"-DCMAKE_OSX_DEPLOYMENT_TARGET={args.macos_min_version}"]
                )

        elif configuration.platform=="ios":
            if generatorName == 'Xcode' and configuration.arch == "std":
                cmakeArguments += ['-DCMAKE_SYSTEM_NAME=iOS']

                xcodeDevPath = subprocess.check_output(['xcode-select', '-p']).decode("utf-8").strip()
                whichCxx = subprocess.check_output(['which', 'c++']).decode("utf-8").strip()

                self.logger.debug("Environment info:")
                self.logger.debug('\t"xcode-select -p": "%s"' % (xcodeDevPath))
                self.logger.debug('\t"which c++": "%s"' % (whichCxx))
                expected_clangxx_location = os.path.join(xcodeDevPath, "Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++")

                if not os.path.isfile(expected_clangxx_location):
                    self.logger.warning(
                        f'Expected file "{expected_clangxx_location}" to exist but it did not'
                    )

            else:
                if configuration.arch in ["std", "simulator"]:
                    cmakeArguments.extend( [ "-DPLATFORM=SIMULATOR64" ] );
                elif configuration.arch == "device":
                    cmakeArguments.extend( [ "-DPLATFORM=OS64" ] );
                else:
                    raise error.InvalidArchitectureError(arch);

                toolChainFileName = "ios.make.toolchain.cmake";

        if toolChainFileName:
            toolChainFilePath = os.path.join(self.rootDirectory, "cmake/toolchains", toolChainFileName);               

            if not os.path.isfile(toolChainFilePath):
                self.logger.error("Required CMake toolchain file not found: %s" , toolChainFilePath);
                return 5;

            cmakeArguments += [f"-DCMAKE_TOOLCHAIN_FILE={toolChainFilePath}"]


        if configuration.config:
            cmakeArguments += [f"-DCMAKE_BUILD_TYPE={configuration.config}"]

        if cmakeArch:
            cmakeArguments += [f"-A {cmakeArch}"]

        if args.cmake_option:
            for option in args.cmake_option:
                cmakeArguments += [f"-D{option}"]

        if needsCleanBuildDir:
            shutil.rmtree(cmakeBuildDir)


        self.cmake.open(self.sourceDirectory, cmakeBuildDir, generatorName, extraGeneratorName = "", extraEnv=cmakeEnvironment)

        self.logger.debug("Starting configure ...")
        self.logger.debug(" Source Directory: %s", self.sourceDirectory)
        self.logger.debug(" Output Directory: %s", cmakeBuildDir)
        self.logger.debug(" Arguments: %s", cmakeArguments)
        self.logger.debug(" Generator: %s", generatorName)


        self.cmake.configure(cmakeArguments)
