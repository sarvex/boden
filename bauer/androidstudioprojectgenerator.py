import os
import tempfile
import shutil
import subprocess
import logging
import sys
import re

from string import Template


def find_defines(app):
    result = []
    if "fileGroups" in app:
        for file_group in app["fileGroups"]:
            if "defines" in file_group:
                result.extend(file_group["defines"])
    return result

def from_defines(defines, key, default):
    for define in defines:
        r = f"{key}=(.*)"
        if match := re.match(r, define):
            return match[1]
    return default


class AndroidStudioProjectGenerator(object):
    def __init__(self, gradle, cmake, platformBuildDir, androidBuildApiVersion):
        self.logger = logging.getLogger(__name__)
        self.project_dir = platformBuildDir;
        self.gradle = gradle
        self.cmake = cmake
        self.androidBuildApiVersion = androidBuildApiVersion
        self.android_support_dir = os.path.normpath(os.path.join(os.path.realpath(__file__), "..", "android-support"))

        self.logger.debug(f"Android support directory: {self.android_support_dir}")

    def getGradleDependency(self):
        return "classpath 'com.android.tools.build:gradle:3.4.2'"

    def prepare_gradle(self):
        # the underlying commandline build system for android is gradle.
        # Gradle uses a launcher script (called the gradle wrapper)
        # that enforces the use of a specific desired gradle version.
        # The launcher script will automatically download the correct
        # version if needed and use that.
        # Any version of gradle can generate the wrapper for any desired
        # version.
        # So now we need to generate the gradle wrapper for "our" version.
        # Right now we use gradle 4.1

        # Unfortunately gradle has the problem that it will try to load the build.gradle files if
        # it finds them in the build directory, even if we only want to generate the wrapper.
        # And loading the build.gradle may fail if the currently installed default
        # gradle version is incorrect.
        # So to avoid this problem we generate the wrapper in a temporary directory and then move it to the desired location.

        gradle_temp_dir = tempfile.mkdtemp();
        try:
            gradle_path = self.gradle.getGradlePath()

            subprocess.check_call(
                f'"{gradle_path}" wrapper --gradle-version=5.3.1',
                shell=True,
                cwd=gradle_temp_dir,
            );

            for name in os.listdir(gradle_temp_dir):
                source_path = os.path.join( gradle_temp_dir, name)
                dest_path = os.path.join( self.project_dir, name)

                if os.path.isdir(dest_path):
                    shutil.rmtree(dest_path)
                elif os.path.exists(dest_path):
                    os.remove(dest_path)

                shutil.move( source_path, dest_path )

        finally:
            shutil.rmtree(gradle_temp_dir)


    def find_applications(self, project, args):
        return [
            target
            for target in project["targets"]
            if target["type"] == "EXECUTABLE"
            and (not args.target or args.target == target["name"])
        ]

    def find_libraries(self, project):
        return [
            target
            for target in project["targets"]
            if target["type"] != "EXECUTABLE"
        ]

    def create_top_level_build_gradle(self):
        gradle_template = Template(open(os.path.join(self.android_support_dir, "top.build.gradle.in"), "r").read())
        result = gradle_template.substitute(gradle_dependency = self.getGradleDependency())

        open(os.path.join(self.project_dir, "build.gradle"), "w").write(result)

    def create_settings_gradle(self, apps):
        module_list = ", ".join([f"""':{target["name"]}'""" for target in apps])

        gradle_template = Template(open(os.path.join(self.android_support_dir, "settings.gradle.in"), "r").read())
        result = gradle_template.substitute(include_list = module_list )
        open(os.path.join(self.project_dir, "settings.gradle"), "w").write(result)

    def create_gradle_properties(self):
        properties_template = Template(open(os.path.join(self.android_support_dir, "gradle.properties.in"), "r").read())
        result = properties_template.substitute()
        open(os.path.join(self.project_dir, "gradle.properties"), "w").write(result)


    def de_unicode(self, string):
        return string.encode("utf-8") if sys.version_info <= (3,0) else string

    def gather_directories(self, app, project):
        targets = self.find_libraries(project)
        targets += [app]

        source_directories = [
            self.de_unicode(target["sourceDirectory"] + "/src")
            for target in targets
        ]
        include_directories = [
            self.de_unicode(target["sourceDirectory"] + "/include")
            for target in targets
        ]
        java_directories = [
            self.de_unicode(target["sourceDirectory"] + "/java")
            for target in targets
        ]

        return (source_directories, include_directories, java_directories)     

    def create_target_build_gradle(self, 
                                   module_directory, 
                                   app, 
                                   project, 
                                   android_abi, 
                                   android_dependencies, 
                                   android_extra_java_directories, 
                                   target_dependencies, 
                                   android_min_sdk_version, 
                                   android_target_sdk_version, 
                                   android_version, android_version_id,
                                   android_package_id):
        self.make_directory(module_directory)
        directories = self.gather_directories(app, project)

        gradle_template = Template(open(os.path.join(self.android_support_dir, "target.build.gradle.in"), "r").read())

        cmakelists_path = os.path.join(project["sourceDirectory"], "CMakeLists.txt").replace('\\', '/')

        abi_filter_string = f"abiFilters '{android_abi}'" if android_abi else ""
        android_dependecy_string = "".join(
            [
                "    implementation '%s'\n" % (dependency)
                for dependency in android_dependencies
            ]
        )
        target_dependency_string = "" #"".join(list( ("    implementation project(':%s')\n" % dependency for dependency in target_dependencies)))
        targets = [app["name"]]
        cmake_target_list = ", ".join([f'"{target}"' for target in targets])

        target_ndk_abi_block = ""

        if android_abi:
            target_ndk_abi_block = """
            ndk {
                abiFilters "%s"
            }""" % ( android_abi )

        result = gradle_template.substitute(
            compile_sdk_version = self.androidBuildApiVersion,
            target_sdk_version = android_target_sdk_version,
            application_id = android_package_id,
            min_sdk_version = android_min_sdk_version,
            version_code = android_version_id,
            version_name = android_version,
            cmake_target_list = cmake_target_list,
            cmake_target_arguments = '"-DANDROID_STL=c++_static", "-DANDROID_CPP_FEATURES=rtti exceptions", "-DBDN_ANDROID_MIN_SDK_VERSION=$minSdkVersion.mApiLevel", "-DBDN_ANDROID_TARGET_SDK_VERSION=$targetSdkVersion.mApiLevel"',
            abi_filter = abi_filter_string, 
            cpp_flags = "-std=c++17 -frtti -fexceptions",
            cmakelists_path = cmakelists_path,
            cmake_version = self.cmake.globalSettings["capabilities"]["version"]["string"],
            jni_src_dir_list = directories[0] + directories[1],
            java_src_dir_list = directories[2] + android_extra_java_directories,
            android_dependencies = android_dependecy_string,
            android_module_dependency_code = target_dependency_string,
            ndk_abi_block = target_ndk_abi_block )

        open(os.path.join(module_directory, "build.gradle"), "w").write(result)

    def create_target_strings_xml(self, module_directory, app):
        directory = self.make_directory(os.path.join(module_directory, "src", "main", "res", "values"))

        strings_template = Template(open(os.path.join(self.android_support_dir, "strings.xml.in"), "r").read())

        strings = f'<string name="app_name">{app["name"]}</string>'
        result = strings_template.substitute( xml_string_entries = strings )

        open(os.path.join(directory, "strings.xml"), "w").write(result)

    def copy_android_manifest(self, module_directory, app):
        directory = self.make_directory(os.path.join(module_directory, "src", "main"))
        build_directory = app['buildDirectory']

        src = os.path.join(build_directory, "AndroidManifest.xml")
        dest = os.path.join(directory, "AndroidManifest.xml")

        shutil.copy(src, dest)

    def copytree(self, src, dst, symlinks=False, ignore=None):
        for root, dirs, files in os.walk(src):
            sub = os.path.relpath(root, src) 
            dir = os.path.join(dst, sub)
            if not os.path.exists(dir):
                os.makedirs(dir)

            for file in files:
                srcfile = os.path.join(root, file)
                destfile = os.path.join(dir, file)
                shutil.copy2(srcfile, destfile)

    def copy_resources(self, app, module_directory):
        self.make_directory(os.path.join(module_directory, "src", "main", "res"))

        resource_source_dir = os.path.join(app["buildDirectory"], "android-resources")
        resource_dest_dir = os.path.join(module_directory, "src", "main")

        if os.path.exists(resource_source_dir):
            self.logger.debug(
                f"Copying resources ( {resource_source_dir} => {resource_dest_dir} )"
            )
            self.copytree(resource_source_dir, resource_dest_dir)

    def generate(self, project, androidAbi, target_dependencies, args):
        if not os.path.isdir(self.project_dir):
            os.makedirs(self.project_dir);

        android_target_sdk_version = self.cmake.cache["BDN_ANDROID_TARGET_SDK_VERSION"]
        android_min_sdk_version = self.cmake.cache["BDN_ANDROID_MIN_SDK_VERSION"]
        android_dependencies = self.cmake.cache["BAUER_ANDROID_DEPENDENCIES"].split(';')
        android_extra_java_directories = list(filter(None, self.cmake.cache["BAUER_ANDROID_EXTRA_JAVA_DIRECTORIES"].split(';')))
        self.logger.debug(f"Dependencies: {android_dependencies}")
        self.logger.debug(f"Extra Java Directories: {android_extra_java_directories}")

        self.prepare_gradle()
        self.create_top_level_build_gradle()

        apps = self.find_applications(project, args)

        self.create_settings_gradle(apps)
        self.create_gradle_properties()

        for app in apps:
            module_directory = os.path.join(self.project_dir, app["name"]);

            defines = find_defines(app)
            android_version = from_defines(defines, "ANDROID_VERSION", "1.0")
            android_version_id = from_defines(defines, "ANDROID_VERSION_ID", "1")
            android_package_id = from_defines(defines, "ANDROID_APP_ID", "io.boden.android.notset")

            resource_directory = os.path.join(module_directory, "src", "main", "res")
            if os.path.exists(resource_directory):
                shutil.rmtree(resource_directory)

            self.create_target_build_gradle(
                module_directory, 
                app, 
                project, 
                androidAbi, 
                android_dependencies, 
                android_extra_java_directories, 
                target_dependencies[app["name"]], 
                android_min_sdk_version, 
                android_target_sdk_version, 
                android_version, 
                android_version_id,
                android_package_id
            )
            self.create_target_strings_xml(module_directory, app)
            self.copy_android_manifest(module_directory, app)
            self.copy_resources(app, module_directory)

    def make_directory(self, path):
        if not os.path.isdir(path):
            os.makedirs(path)

        return path

