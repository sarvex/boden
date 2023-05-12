import tempfile
import os
import sys
import subprocess
import logging
import zipfile
import shutil
import stat

def download_file(url, file_path):
    if sys.version_info[0]>=3:
        import urllib.request
        urllib.request.urlretrieve(
                        url,
                        file_path)
    else:
        import urllib2
        resp = urllib2.urlopen(url)

        with open(file_path, "wb") as f:
            shutil.copyfileobj(resp, f)

class Gradle:
    def __init__(self, rootPath):
        self.logger = logging.getLogger(__name__)
        self.gradlePath = None
        self.rootPath = rootPath

    def stop(self):
        self.logger.debug(f"Calling {self.getGradlePath()} --stop")
        subprocess.call(f'"{self.getGradlePath()}" --stop', shell=True);


    def getGradlePath(self):
        if self.gradlePath is None:        

            # first try to call an installed gradle version.

            outFile, outFilePath = tempfile.mkstemp()
            try:
                result = subprocess.call("gradle --version", shell=True, stdout=outFile, stderr=subprocess.STDOUT)
            finally:
                os.close(outFile)
                os.remove(outFilePath)

            if result==0:
                self.gradlePath = "gradle"

            else:
                self.logger.debug("No system gradle found, using own...")
                # no system gradle
                gradle_base_dir = os.path.join(self.rootPath, "3rdparty_build", "gradle")

                gradle_version_name = "gradle-5.3.1"

                gradle_path = os.path.join(gradle_base_dir, gradle_version_name, "bin", "gradle");
                if sys.platform == "win32":
                    gradle_path += ".bat"

                if not os.path.exists(gradle_path):
                    if not os.path.isdir(gradle_base_dir):
                        os.makedirs(gradle_base_dir)

                    self.logger.info("Downloading gradle...")

                    gradle_zip_file_name = f"{gradle_version_name}-bin.zip"

                    gradle_download_file = os.path.join(gradle_base_dir, gradle_zip_file_name)

                    download_file(
                        f"https://services.gradle.org/distributions/{gradle_zip_file_name}",
                        gradle_download_file,
                    )

                    self.logger.info("Extracting gradle...")

                    zipf = zipfile.ZipFile(gradle_download_file, 'r')
                    zipf.extractall(gradle_base_dir)
                    zipf.close()

                    os.remove(gradle_download_file)

                    if sys.platform!="win32":
                        self.logger.debug("Setting executable flag for gradle...")
                        os.chmod(gradle_path, stat.S_IXUSR|stat.S_IRUSR)

                    if not os.path.exists(gradle_path):
                        raise Exception(
                            f"Gradle executable not found after fresh download. Expected here: {gradle_path}"
                        )

                self.gradlePath = gradle_path

        return self.gradlePath

