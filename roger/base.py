import os
import sys
import logging
import shutil
import errno

from resource_file import ResourceFile
import Exe2Img

class Roger:
    def __init__(self):
        self.resource_file = ResourceFile()

    def full_path(self, path):
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.resource_file.root_path, path))

    def make_directories(self, folder):
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise 

    def copy(self, args, src, dest):
        folder = os.path.dirname(dest)
        src = self.full_path(src)

        if args.action == 'build':
            logging.debug(f"Copying {src} => {dest}")
            self.make_directories(folder)  

            shutil.copyfile(src, dest)
        else:
            sys.stdout.write(os.path.abspath(src).replace('\\', '/'))
            sys.stdout.write("\\;")
            sys.stdout.write(os.path.abspath(dest).replace('\\', '/'))
            sys.stdout.write(";")
        return True

    def get_source_image(self, args, resolution):
        r = resolution
        if type(r) is dict and "execute" in r:
            command = r['execute']
            input_file = self.full_path(r['file'])
            if args.action == "dependencies":
                return input_file

            output_type = r['output-type']

            return Exe2Img.create(command, input_file, output_type)

        return r

    def copy_image(self, args, lang_folder_name, bundle_path, resolutions, resolutionId, suffix):
        if resolutionId in resolutions and len(resolutions[resolutionId]) > 0:
            source_image = self.get_source_image(args, resolutions[resolutionId])
            return self.copy_file(args, lang_folder_name, source_image, bundle_path, suffix)
        return False