from __future__ import print_function

import sys, json, os, shutil, cmakelib
import argparse
import traceback
import error
import logging

from bauerargparser import BauerArgParser
from bauerargparser import HelpOptionUsed
from commandprocessor import CommandProcessor
from buildfolder import BuildFolder
from bauerutilities import BauerGlobals
from generatorinfo import GeneratorInfo
from coloredlogger import ColorizingStreamHandler
from templatecreator import TemplateCreator
from documentation import Documentation


def setupLogging(argv):
    root = logging.getLogger()
    colorizer = ColorizingStreamHandler()
    root.addHandler(colorizer)

    if '--enable-debug-output' in argv or '-d' in argv:
        colorizer.setFormatter(logging.Formatter("[%(asctime)s](%(name)s): %(message)s"))
        root.setLevel(logging.DEBUG)
    else:
        colorizer.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
        root.setLevel(logging.INFO)

def run(argv):
    bauerGlobals = BauerGlobals()

    setupLogging(argv)

    generatorInfo = GeneratorInfo();

    argParser = BauerArgParser(bauerGlobals, generatorInfo);
    argParser.buildBauerArguments(argv)

    args = argParser.parse_args()

    if args is None:
        return

    if args.command == 'new':
        templateCreator = TemplateCreator()
        templateCreator.generate(args)
        return
    if args.command == 'doc':
        doccer = Documentation()
        doccer.run(args)
        return

    rootPath = os.path.abspath(os.path.join(os.path.realpath(__file__), "..", ".."))
    source_folder = os.getcwd()

    # Python will switch to the real path when the working dir has a symlink in it.
    # We'll update the current dir and the environment variable to reflect this.
    os.chdir(source_folder)
    os.environ["PWD"] = source_folder

    buildFolder = BuildFolder(bauerGlobals, generatorInfo, source_folder, args)

    commandProcessor = CommandProcessor(bauerGlobals, generatorInfo, args, rootPath, source_folder, buildFolder)
    commandProcessor.process()

def main(argv):
    try:
        return run(argv)
    except HelpOptionUsed as e:
        exit(0)
    except cmakelib.CMakeError as e:

        if '-d' in argv:
            print(f"CMake error: {e.cmakeError}", file=sys.stderr)
            print(" packet:", e.packet, file=sys.stderr)
            traceback.print_exc();
        else:
            print(" ".join(str(v) for v in e.arg), file=sys.stderr)
        exit(1)

    except error.ErrorWithExitCode as e:
        if '-d' in argv:
            traceback.print_exc();
        else:
            print("Error: %s (%i)" % ( e.errorMessage, e.exitCode ))

        exit(e.exitCode);

    except Exception as e:        
        traceback.print_exc();
        exit(50)
