"""
Setup script for data_api Python packages and scripts.
"""
import setuptools
import glob
import logging
import os
import subprocess
import shutil
import sys

# Logging

#logging.basicConfig()
_log = logging.getLogger('setup')
_h = logging.StreamHandler()
_h.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(name)s: %('
                                  'message)s'))
_log.addHandler(_h)
vb = sum([len(a) - 1 if a.startswith('-v') else 0 for a in sys.argv[1:]])
_log.setLevel([logging.WARN, logging.INFO, logging.DEBUG][min(vb, 2)])

# Globals

version = open('VERSION').read().strip()
packages = setuptools.find_packages("lib")
g_with_jupyter = False

server_languages = ["python_server"]
client_languages = ["python", "javascript", "perl", "java"]

class BuildAttr(object):
    """Attributes for building Thrift clients and servers.
    This wrapper class greatly improves the aesthetics of the code.
    """
    def __init__(self, values):
        self.style = values['style']
        self.generated_dir = values['generated_dir']
        self.copy_files = values['copy_files']
        self.rename_files = values.get('rename_files', {})

# There are two sets of python code generated.
# The python server code is twisted based and contains an async client.
# The default python client code is synchronous and not based on twisted.
# When building the server code, we generate both sets of code and then rename
# the generated synchronous code to thrift_client.py to not overwrite the
# twisted service code.
thrift_build = {
    "python_server": BuildAttr({
        "style": "py:twisted",
        "generated_dir": "gen-py.twisted",
        "copy_files": ["constants.py", "ttypes.py", "thrift_service.py"],
    }),
    "python": BuildAttr({
        "style": "py:new_style",
        "generated_dir": "gen-py",
        "copy_files": ["constants.py", "ttypes.py", "thrift_service.py"],
        "rename_files": {"thrift_service.py": "thrift_client.py"}
    }),
    "javascript": BuildAttr({
        "style": "js:jquery",
        "generated_dir": "gen-js",
        "copy_files": ["*"]
    }),
    "perl": BuildAttr({
        "style": "perl",
        "generated_dir": "gen-perl",
        "copy_files": ["Constants.pm", "Types.pm", "thrift_service.pm"]
    }),
    "java": BuildAttr({
        "style": "java:sorted_containers",
        "generated_dir": "gen-java",
        "copy_files": ["*"]
    })
}


# Functions

def filter_args():
    global g_with_jupyter
    setup_args = sys.argv[1:]

    # TODO: Put this new option into --help output

    if "--jupyter" in setup_args:
        g_with_jupyter = True
        setup_args.remove("--jupyter")

    return setup_args


def get_dependencies():
    def parse_requirements(filename):
        pkg = list()
    
        with open(filename, 'r') as req_file:
            req_lines = req_file.read().splitlines()
        
            for line in req_lines:
                if line.strip() == "":
                    pass
                elif line.startswith("-r"):
                    pkg.extend(parse_requirements(line.split(" ")[-1]))
                else:
                    pkg.append(line)
        return pkg

    setup_args = sys.argv[1:]

    if g_with_jupyter:
        install_requires = parse_requirements(
            os.path.join(os.path.dirname(__file__),"requirements-jupyter.txt"))
        open(os.path.join(os.path.dirname(__file__),'exclude-tests.txt'), 'w').write('') # clear it
    else:
        _log.warn("--jupyter not specified, so using minimal install "
                  "without packages in doekbase.data_api.interactive")
        exclude_pkg = 'doekbase.data_api.interactive'

        global packages
        if exclude_pkg in packages:
            packages.remove(exclude_pkg)

        install_requires = parse_requirements(
            os.path.join(os.path.dirname(__file__),"requirements.txt"))
        open(os.path.join(os.path.dirname(__file__),'exclude-tests.txt'), 'w')\
            .write('lib/' + exclude_pkg.replace('.', '/'))
        # clear it

    _log.debug('Install requirements: {}'.format(install_requires))
    return install_requires

def call_command(command, is_thrift=False):
    """Better exception when calling a command."""
    cstr = ' '.join(command) if isinstance(command, list) else command
    _log.debug('Run command "{}"'.format(cstr))
    try:
        errno = subprocess.call(command)
    except Exception as err:
        if is_thrift:
            sys.stderr.write("==\nUnable to run `thrift` executable, is Apache "
                             "Thrift installed? See https://thrift.apache.org/ "
                             "for help\n==\n")
            raise RuntimeError('Cannot run Thrift ({c}): {'
                               'e}'.format(c=cstr, e=err))
        else:
            raise RuntimeError('Command "{c}" failed: {e}'.format(c=cstr,
                                                                  e=err))
    return errno

def set_thrift_version(filename, version):
    """Set current version string to be the contents of a special Thrift spec file.
    """
    fp = file(filename, 'w')
    fp.write('const string VERSION = "{}"\n'.format(version))
    fp.close()
    print("Set Thrift spec version: {}".format(version))

def preprocess_thrift(target_file, include_dir):
    """Pre-process a Thrift spec file to handle custom include statements.
    """
    print("Preprocessing file: {}".format(target_file))
    script = os.path.join('bin', 'data_api_preprocess_thrift')
    command = [script, '-I', include_dir, target_file]
    try:
        output = subprocess.check_output(command)
    except subprocess.CalledProcessError as err:
        raise RuntimeError('Preprocessing failed. Command {c} returned: {o}'
                           .format(c=' '.join(command), o=err.output))
    except Exception as err:
        raise RuntimeError('Preprocessing failed. Command: {c}'
                           .format(c=' '.join(command)))
    print("Preprocessing OK: {}".format(output.strip()))

class BuildThriftClients(setuptools.Command):
    """Build command for generating Thrift client code"""

    user_options = []

    def initialize_options(self):
        pass


    def finalize_options(self):
        pass


    def run(self):
        _log.info('Build Thrift code')
        try:
            self._try_run()
        except Exception as err:
            _log.error("error in BuildThriftClients.run: {}".format(err))
            raise

    def _try_run(self):
        spec_base_path = "thrift/specs"
        dest_base_path = "thrift/stubs"
        spec_inc_obj = spec_base_path + "/object"
        spec_common_path = os.path.join(spec_base_path, 'common')
        set_thrift_version(os.path.join(spec_common_path, 'version.thriftinc'), version)
        for dirpath, dirnames, filenames in os.walk(spec_base_path):
            for f in filter(lambda _: _.endswith('.thrift'), filenames):
                spec_path = os.path.abspath(os.path.join(dirpath, f))
                preprocess_thrift(spec_path, spec_common_path)
                # Process each language
                for lang in client_languages:
                    settings = thrift_build[lang]  # settings for current lang.
                    # Remove old generated files, if any
                    if os.path.exists(settings.generated_dir):
                        shutil.rmtree(settings.generated_dir)
                    # Run Thrift compiler to generate new stubs
                    cmd = ["thrift",  "-I", spec_inc_obj, "-r", "--gen"]
                    cmd.append(settings.style)
                    cmd.append(spec_path)
                    _log.debug("{}: Thrift command = {}".format(lang, cmd))
                    errno = call_command(cmd, is_thrift=True)
                    if errno != 0:
                        raise Exception("Thrift build for {} failed with : {}"
                                        .format(lang, errno))
                    # Get a list of all generated stub files
                    generated_files = glob.glob(settings.generated_dir + "/*/*")
                    if len(generated_files) == 0:
                        generated_files = glob.glob(thrift_build[
                                                        lang].generated_dir + "/*")
                    # Copy generated files to their final place in the tree
                    copied = False
                    if settings.copy_files == ["*"]:
                        destination = spec_path.rsplit("/",1)[0].replace(
                            "specs", "stubs/" + lang)
                        for name in generated_files:
                            source = os.path.basename(name)
                            shutil.copyfile(name, os.path.join(destination,
                                                            source))
                        copied = len(generated_files) > 0
                    else:
                        for x in generated_files:
                            for name in settings.copy_files:
                                if name == os.path.basename(x):
                                    thrift_file_path, _ = spec_path.rsplit("/", 1)
                                    if lang == 'pythonhahaha' and name == 'object.thrift':
                                        # For Python, move copies of 'object' package under each subdir
                                        pass # STOPPED
                                    else:
                                        dest_path = thrift_file_path.replace("specs", "stubs/" + lang)
                                        shutil.copyfile(x, os.path.join(dest_path, name))
                                copied = True
                    if not copied:
                        raise Exception("Unable to find thrift-generated "
                                        "files to copy!")

        # Remove original generated directories
        for lang in client_languages:
            settings = thrift_build[lang]
            shutil.rmtree(settings.generated_dir)


class BuildThriftServers(setuptools.Command):
    """Build command for generating Thrift server code"""

    user_options = []

    def initialize_options(self):
        pass


    def finalize_options(self):
        pass


    def run(self):
        _log.info('Install Thrift code')
        try:
            self._try_run()
        except Exception as err:
            _log.error("error in CustomInstall.run: {}".format(err))
            raise

    def _try_run(self):
        spec_base_path = "thrift/specs"
        spec_inc_obj = spec_base_path + "/object"
        spec_common_path = os.path.join(spec_base_path, 'common')
        set_thrift_version(os.path.join(spec_common_path, 'version.thriftinc'), version)
        start_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), spec_base_path)
        for dirpath, dirnames, filenames in os.walk(start_path):
            for f in filenames:
                if f.endswith(".thrift"):
                    spec_path = os.path.abspath(os.path.join(dirpath, f))
                    preprocess_thrift(spec_path, spec_common_path)
                    # first generate all the twisted server code
                    settings = thrift_build['python_server']

                    command = ["thrift",  "-I", spec_inc_obj, "-r", "--gen"]
                    command.append(settings.style)
                    command.append(spec_path)
                    errno = call_command(command, is_thrift=True)
                    if errno != 0:
                        raise Exception("Thrift build for python service failed with : {}".format(errno))

                    generated_files = glob.glob(settings.generated_dir + "/*/*")

                    if len(generated_files) == 0:
                        generated_files = glob.glob(settings.generated_dir +
                                                    "/*")
                    # now copy the generated server files to the target
                    copied = False
                    for x in generated_files:
                        for name in settings.copy_files:
                            if name in x:
                                destination = os.path.join(dirpath.replace(
                                    "thrift/specs", "lib/doekbase/data_api")
                                                           + "/service/", name)
                                shutil.copyfile(x, destination)
                                copied = True
                    if not copied:
                        raise Exception("Unable to find thrift service generated"
                                        " files to copy!")
                    shutil.rmtree(settings.generated_dir)

                    # generate the client code
                    settings = thrift_build['python']
                    command = ["thrift", "-r", "--gen"]
                    command.append(settings.style)
                    command.append(spec_path)
                    errno = call_command(command, is_thrift=True)
                    if errno != 0:
                        raise Exception("Thrift build for python client failed "
                                        "with : {}".format(errno))

                    generated_files = glob.glob(settings.generated_dir + \
                        "/*/*")

                    if len(generated_files) == 0:
                        generated_files = glob.glob(settings.generated_dir
                        + \
                            "/*")

                    # rename the thrift_service.py generated to thrift_client.py
                    renamed = False
                    for x in generated_files:
                        for name in settings.rename_files:
                            if name in x:
                                destination = os.path.join(dirpath.replace(
                                    "thrift/specs", "lib/doekbase/data_api") +
                                                           "/service/",
                                                           settings.rename_files[name])
                                shutil.copyfile(x, destination)
                                renamed = True
                    if not renamed:
                        raise Exception("Unable to find thrift client generated"
                                        " files to copy!")
                    shutil.rmtree(settings.generated_dir)


config = {
    "description": "KBase Data API",
    "author": "Matt Henderson",
    "url": "https://github.com/kbase/data_api/",
    "download_url": "https://github.com/kbase/data_api/stuff?download",
    "author_email": "mhenderson@lbl.gov",
    "version": version,
    "setup_requires": ["six"],
    "tests_require": ["nose", "nose-timer", "codecov"],
    "packages": packages,
    "scripts": ["bin/data_api_demo.py",
                "bin/data_api_benchmark.py",
                "bin/dump_wsfile",
                "bin/data_api_start_service.py",
                "bin/assembly_client_driver.py",
                "bin/genome_annotation_client_driver.py",
                "bin/taxon_client_driver.py",
                "bin/test_api_service.py",
                "bin/extract_thrift_docs",
                "bin/data_api_preprocess_thrift"],
    "name": "doekbase_data_api",
    "entry_points": {
        'nose.plugins.0.10': [
            'wsurl = doekbase.data_api.tests.nose_plugin_wsurl:WorkspaceURL'
        ]
    },
    "zip_safe": True
}

setuptools.setup(package_dir = {'': 'lib'},
                 script_args = filter_args(),
                 install_requires = get_dependencies(),
                 cmdclass = {'build_thrift_servers': BuildThriftServers,
                             'build_thrift_clients': BuildThriftClients},
                 **config)
