import argparse
import logging
import os
import sys
import subprocess
import random
import time
import plistlib
import tempfile

import error
import bauer
from iosinfo import IOSInfo
from bauerargparser import BauerArgParser


class IOSRunner:
    def __init__(self, cmake):
        self.logger = logging.getLogger(__name__)

        self.cmake = cmake

        self.iosInfo = IOSInfo()
        self.ios_simulator_device_type = None
        self.ios_simulator_os          = None
        self.ios_device_id             = None

    def run(self, configuration, args):

        cmakeTargetToRun = self.cmake.executableTarget(args.config, args.target)
        artifactToRun = self.cmake.executableArtifactPath(cmakeTargetToRun)
        artifactToRun = artifactToRun.replace("${EFFECTIVE_PLATFORM_NAME}", "-iphonesimulator")

        return self.runExecutable(artifactToRun, args)

    def runExecutable(self, artifactToRun, args):
        self.ios_simulator_device_type = self.iosInfo.getSelectedDeviceType(args)
        self.ios_simulator_os = self.iosInfo.getSelectedOS(args)
        self.ios_device_id = args.ios_device_id

        self.logger.debug("IOS Device type:  %s", self.ios_simulator_device_type)
        self.logger.debug("IOS Simulator OS: %s", self.ios_simulator_os)
        self.logger.debug("IOS Device ID: %s", self.ios_device_id)

        self.logger.debug("Executable: %s", artifactToRun)

        if not artifactToRun:
            raise error.ProgramArgumentError(
                f"Couldn't find path to exectuable for Module {args.target}"
            )

        if artifactToRun.endswith('.app') and os.path.isdir(artifactToRun):
            r = self.readPList(os.path.join(artifactToRun, "Info.plist"))
            executable = r["CFBundleExecutable"]
            artifactToRun = os.path.join(artifactToRun, executable)

        if not os.path.exists(artifactToRun):
            raise error.ProgramArgumentError(
                f"exectuable for Module {args.target} does not exists at: {artifactToRun}"
            )

        bundlePath = self.getBundlePathFromExecutable(artifactToRun)

        bundleId = self.getBundleIdentifier(bundlePath)
        self.logger.debug("Bundle Identifier: %s", bundleId)

        simulatorId = None
        try:
            if self.ios_device_id is None:
                simulatorId = self.createSimulatorDevice()
                self.logger.debug("Simulator Id: %s", simulatorId)
                self.bootSimulator(simulatorId)

            else:
                simulatorId = self.ios_device_id
            self.installApp(simulatorId, bundlePath)
            processId = self.startApp(simulatorId, bundleId, args)
        finally:
            if simulatorId and not self.ios_device_id:
                self.shutdownSimulator(simulatorId)

        return 0
     
    def createSimulatorDevice(self):
        simulatorName = f"bdnTestSim-{random.getrandbits(32)}"

        self.logger.debug("Simulator name: %s", simulatorName)

        arguments = ["xcrun", "simctl", "create", simulatorName, 
            self.ios_simulator_device_type, 
            self.ios_simulator_os]

        simulatorId = subprocess.check_output(" ".join(arguments), shell=True).strip().decode(encoding='utf-8')

        if not simulatorId or " " in simulatorId or "\n" in simulatorId:
            raise Exception("Invalid simulator device ID returned.")

        return simulatorId

    def bootSimulator(self, simulatorId):
        self.logger.info("Booting simulator ...")
        subprocess.check_call("open -a Simulator", shell=True)

        # note that this will fail if the simulator is already booted or is currently booting up.
        # That is ok.
        subprocess.call(f"xcrun simctl boot {simulatorId}", shell=True)

        self.waitForSimulatorStatus(simulatorId, "booted", 600)

    def installApp(self, simulatorId, bundlePath):
        self.logger.info("Installing Application in simulator ...")
        cmdLine = f'xcrun simctl install "{simulatorId}" "{bundlePath}"'
        self.logger.debug(f"Starting: {cmdLine}")
        subprocess.check_output(cmdLine, shell=True)

    def startApp(self, simulatorId, bundleId, args):
        self.logger.info("Starting Application ...")

        # --console connects the app's stdout and stderr to ours and blocks indefinitely
        stdoutOptions = []
        self.stdOutFileName = ""
        if args.run_output_file:
            self.stdOutFileName = os.path.abspath(args.run_output_file);
            if os.path.exists(self.stdOutFileName):
                os.remove(self.stdOutFileName)

            self.logger.debug("Redirecting Applications stdout to: %s", self.stdOutFileName)
        else:
            tf = tempfile.NamedTemporaryFile(mode='w+b', delete=False)
            self.stdOutFileName = tf.name


        arguments = ["xcrun",  "simctl", "launch", "--console-pty" ] + [simulatorId, bundleId] + args.params

        commandLine = ' '.join('"{0}"'.format(arg) for arg in arguments)
        commandLine += f" > {self.stdOutFileName} 2>&1 ";

        self.logger.debug(f"Starting: {commandLine}")

        result = subprocess.check_call( commandLine , shell=True)

        if result != 0:
            self.logger.warning("There was an issue running the app")

        try:
            with open(self.stdOutFileName) as fp:
                self.logger.info("Application output:\n\n%s" % (fp.read()))
        except:
            pass

        if not args.run_output_file:
            os.remove(self.stdOutFileName)


    #def waitForAppToExit(self, simulatorId, processId, bundleId):
    #    self.logger.info("Waiting for simulated process %s to exit ...", processId)

    #    while True:
    #        processListOutput = subprocess.check_output('xcrun simctl spawn "%s" launchctl list' % simulatorId, shell=True).decode(encoding='utf-8')

    #        foundProcess = False
    #        for line in processListOutput.splitlines():

    #            words = line.split()

    #            if words[0]==processId and bundleId in str(line):
    #                foundProcess = True
    #                break

    #        if not foundProcess:
    #            self.logger.info("Process inside simulator has exited.")
    #            break

    #        time.sleep(2)


    def shutdownSimulator(self, simulatorId):
        self.logger.info("Shutting down simulator");
        subprocess.call(f'xcrun simctl shutdown "{simulatorId}"', shell=True);
        # note that shutdown automatically waits until the simulator has finished shutting down

        self.logger.info("Deleting simulator device.");
        subprocess.call(f'xcrun simctl delete "{simulatorId}"', shell=True)

    def waitForSimulatorStatus(self, simulatorId, wait_for_status, timeout_seconds):
        timeout_time = time.time()+timeout_seconds
        while True:

            status = self.getSimulatorStatus(simulatorId)
            if not status:
                raise Exception("Unable to get simulator status.")

            self.logger.debug("Simulator status: %s", status);

            if status==wait_for_status:
                break

            if time.time() > timeout_time:
                raise Exception("Simulator has not reached desired status in %d seconds - timing out." % timeout_seconds)

            time.sleep(1)

    def getSimulatorStatus(self, simulatorId):
        output = subprocess.check_output("xcrun simctl list", shell=True).decode(encoding='utf-8')

        search_for = f"({simulatorId})"

        for line in output.splitlines():
            if search_for in line:
                before, sep, status = line.rpartition("(")
                if sep:
                    status, sep, after = status.partition(")")
                if sep and status:
                    return status.lower()

        return None

    def getBundlePathFromExecutable(self, executablePath):
        return os.path.abspath(os.path.join( executablePath, ".."))

    def readPList(self, plistPath):
        self.logger.info("Reading plist at %s", plistPath)
        if sys.version_info >= (3, 0):
            return plistlib.load( open(plistPath, "rb") )
        tf = tempfile.NamedTemporaryFile(mode='w+b', delete=False)
        os.system(f'plutil -convert xml1 {plistPath} -o {tf.name}')
        return plistlib.readPlist(open(tf.name, "rb"))

    def getBundleIdentifier(self, bundlePath):
        plistPath = os.path.abspath(os.path.join( bundlePath, "Info.plist"))

        r = self.readPList(plistPath)

        return r["CFBundleIdentifier"] 

def main():
    bauer.setupLogging(sys.argv)

    argParser = BauerArgParser(None, None)
    parser = argparse.ArgumentParser()
    argParser.setBaseParser(parser)

    parser.add_argument('-t', '--target', help='path to the ios app to run', required=True)
    argParser.addSimulatorArguments(parser)
    argParser.addIOSSimulatorArguments(parser)
    argParser.buildGlobalArguments([parser])
    argParser.addParams(parser)
    args = parser.parse_args()

    runner = IOSRunner(None)
    runner.runExecutable(args.target, args)

if __name__ == "__main__":
    main()
