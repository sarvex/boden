import os
import logging

from buildconfiguration import BuildConfiguration

def listDirectories(dir):
    return next(os.walk(dir))[1]

class BuildFolder:
    def __init__(self, bauerGlobals, generatorInfo, rootPath, args):
        self.args = args
        self.bauerGlobals = bauerGlobals
        self.generatorInfo = generatorInfo
        self.logger = logging.getLogger(__name__)

        if args.build_folder is None:
            self.buildfolder = os.path.join(rootPath, "build")

        else:
            self.buildfolder = os.path.abspath(args.build_folder)
            self.logger.debug(f"Build folder: {self.buildfolder}")

    def getBaseBuildDir(self):
        return self.buildfolder

    # Scans for existing build configurations
    def getExistingBuildConfigurations(self):
        buildDir = self.getBaseBuildDir()
        prepared = []
        if os.path.isdir(buildDir):
            for platform in listDirectories(buildDir):
                if platform not in self.bauerGlobals.platformMap:
                    continue

                for arch in listDirectories(os.path.join(buildDir, platform)):
                    for buildsystem in listDirectories(os.path.join(buildDir, platform, arch)):
                        if self.generatorInfo.isSingleConfigBuildSystem(self.generatorInfo.getBuildSystemForFolderName(buildsystem)):
                            prepared.extend(
                                BuildConfiguration(
                                    platform=platform,
                                    arch=arch,
                                    buildsystem=buildsystem,
                                    config=config,
                                )
                                for config in listDirectories(
                                    os.path.join(
                                        buildDir, platform, arch, buildsystem
                                    )
                                )
                                if os.path.exists(
                                    os.path.join(
                                        buildDir,
                                        platform,
                                        arch,
                                        buildsystem,
                                        config,
                                        '.generateProjects.state',
                                    )
                                )
                            )
                        elif os.path.exists( os.path.join(buildDir, platform, arch, buildsystem, '.generateProjects.state') ):
                            prepared.append( BuildConfiguration(platform=platform, arch=arch, buildsystem=buildsystem, config=None) )
        return prepared

    # Returns the closest match to the user selected configuration
    def getMatchingBuildConfigurations(self, existingConfigurations):
        matches = []

        for configuration in existingConfigurations:
            if self.args.platform not in [None, configuration.platform]:
                continue
            if self.args.arch not in [None, configuration.arch]:
                continue
            if self.args.build_system not in [None, configuration.buildsystem]:
                continue
            if (
                self.args.config is None
                or configuration[3] is None
                or self.args.config == configuration.config
            ):
                matches.append(configuration)

        return matches

    def getBuildConfigurationsForCommand(self):
        existingConfigurations = self.getExistingBuildConfigurations()
        self.logger.debug("Existing configurations:")
        for configuration in existingConfigurations:
            self.logger.debug("* %s", configuration)

        matchedConfigurations = self.getMatchingBuildConfigurations(existingConfigurations)

        # User specified configuration:
        if self.args.platform != None and self.args.build_system != None:
            if len(matchedConfigurations) > 0 and self.args.arch is None:
                return matchedConfigurations

            isSingleConfigBuildSystem = self.generatorInfo.isSingleConfigBuildSystem(self.args.build_system)

            if not isSingleConfigBuildSystem or self.args.config != None:
                arch = self.args.arch
                if not arch:
                    arch = 'std'

                config = None if not isSingleConfigBuildSystem else self.args.config
                return [
                    BuildConfiguration(
                        platform=self.args.platform,
                        arch=arch,
                        buildsystem=self.args.build_system,
                        config=config,
                    )
                ]
        return matchedConfigurations

    def getBuildDir(self, configuration):
        result = self.getBaseBuildDir()

        result = os.path.join(result, *filter(None, list(configuration)))

        return result
