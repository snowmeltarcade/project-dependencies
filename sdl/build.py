import os
import shutil
import platform
import argparse
import subprocess
import zipfile

sdlVersion = "2.28.3"
sdlGitURL = "https://github.com/libsdl-org/SDL.git"

gitPath = shutil.which("git")
cmakePath = shutil.which("cmake")
curlPath = shutil.which("curl")

def configureArguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--version", action="store", required=False, help="version to install")
    parser.add_argument("-ios", "--build-ios", action="store_true", required=False, help="build iOS binaries")
    parser.add_argument("-fb", "--force-build", action="store_true", required=False, help="build even if a binary was released in the repo")
    args = parser.parse_args()

    return args


def createDirectories(path):
    print(f"Creating directory: {path}")

    try:
        os.makedirs(path)
    except OSError as error:
        print(error)


def removeDirectory(path):
    print(f"Removing directory: {path}")

    try:
        shutil.rmtree(path)
    except OSError as error:
        print(error)


def runCmd(cmd, cwd=None):
    print(f"Running command: {cmd}")
    subprocess.run(cmd, cwd=cwd)


def runCmdIgnoreError(cmd):
    print(f"Running command: {cmd}")
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"Failed to run cmd: {cmd}")
        return False
    else:
        print(f"Failed to run cmd with unknown error: {cmd}")
        return False


def build(buildiOS, tempDirPath):
    print("Starting build...")

    if platform.system() != "Darwin" and buildiOS:
        print("Can only build iOS on MacOS.")
        return

    createDirectories(tempDirPath)

    os.chdir(tempDirPath)

    # get the latest SDL code
    cmd = [gitPath, "clone", f"{sdlGitURL}"]
    runCmd(cmd)

    os.chdir(os.path.join(os.getcwd(), "SDL"))

    # checkout the version we want
    cmd = [gitPath, "checkout", f"tags/release-{sdlVersion}", "-b", f"release-{sdlVersion}"]
    runCmd(cmd)

    if buildiOS:
        # as of version 2.0.14, the cmake ios build isn't working
        buildDir = os.path.join(os.getcwd(), "build-scripts")
        os.chdir(buildDir)

        cmd = ["./iosbuild.sh"]
        runCmd(cmd)
    else:
        # build with cmake
        buildDir = os.path.join(os.getcwd(), "build")
        createDirectories(buildDir)
        os.chdir(buildDir)

        cmd = [cmakePath, ".."]
        runCmd(cmd)

        cmd = [cmakePath, "--build", ".", "--config", "Release"]
        runCmd(cmd)

    os.chdir(cwd)

    print("Finished build.")


def saveResults(buildiOS, tempDirPath):
    print("Saving results...")

    if buildiOS:
        print("Saving results for iOS...")

        # save ios
        includePath = os.path.join(tempDirPath, "SDL", "build-scripts", "platform", "arm64-ios", "include", "SDL2")
        buildDir = os.path.join(tempDirPath, "SDL", "build-scripts", "platform", "arm64-ios", "lib")

        platformLibName = getPlatformLibName(True, False)

        destLibDir = os.path.join(os.getcwd(), "lib", platformLibName)

        saveBinaries(destLibDir, includePath, platformLibName, buildDir)

        # save ios simulator
        includePath = os.path.join(tempDirPath, "SDL", "build-scripts", "platform", "x86_64-sim", "include", "SDL2")
        buildDir = os.path.join(tempDirPath, "SDL", "build-scripts", "platform", "x86_64-sim", "lib")

        platformLibName = getPlatformLibName(False, True)

        destLibDir = os.path.join(os.getcwd(), "lib", platformLibName)

        saveBinaries(destLibDir, includePath, platformLibName, buildDir)

        print("Saved results for iOS.")
    else:
        print("Saving results for current platform...")

        sdlPath = os.path.join(tempDirPath, "SDL")
        buildDir = os.path.join(sdlPath, "build")
        includePath = os.path.join(sdlPath, "include")

        if platform.system() == "Windows":
            buildDir = os.path.join(buildDir, "Release")

        platformLibName = getPlatformLibName(False, False)

        destLibDir = os.path.join(os.getcwd(), "lib", platformLibName)

        saveBinaries(destLibDir, includePath, platformLibName, buildDir)
        
        print("Saved results for current platform...")

    print("Saved results.")


def saveBinaries(destLibDir, includePath, platformLibName, buildDir):
    createDirectories(destLibDir)

    zipDir = getZipPath(destLibDir, platformLibName)

    with zipfile.ZipFile(zipDir, "w") as zip:
        for root, dirs, files in os.walk(includePath):
            for file in files:
                zip.write(os.path.join(root, file), os.path.join("include", "SDL2", file))

        if platform.system() == "Windows":
            zip.write(os.path.join(buildDir, "SDL2.dll"), "SDL2.dll")
            zip.write(os.path.join(buildDir, "SDL2.lib"), "SDL2.lib")
            zip.write(os.path.join(buildDir, "SDL2.exp"), "SDL2.exp")
            zip.write(os.path.join(buildDir, "SDL2-static.lib"), "SDL2-static.lib")
            zip.write(os.path.join(buildDir, "SDL2main.lib"), "SDL2main.lib")
        elif platform.system() == "Darwin":
            zip.write(os.path.join(buildDir, "libSDL2-2.0.dylib"), "libSDL2.dylib")
            zip.write(os.path.join(buildDir, "libSDL2.a"), "libSDL2.a")
            zip.write(os.path.join(buildDir, "libSDL2main.a"), "libSDL2main.a")
        else:
            zip.write(os.path.join(buildDir, "libSDL2.a"), "libSDL2.a")
            zip.write(os.path.join(buildDir, "libSDL2main.a"), "libSDL2main.a")


def getPlatformLibName(buildiOS, buildiOSSimulator):
    if platform.system() == "Darwin":
        if buildiOS:
            return "iOS"
        elif buildiOSSimulator:
            return "iOS_Simulator"

    return platform.system()


def getZipPath(destLibDir, platformLibName):
    return os.path.join(destLibDir, f"{sdlVersion}_{platformLibName}.zip")


def doesNeedBuilding(buildiOS):
    # only check if the iOS builds are here
    platformLibName = getPlatformLibName(buildiOS, False)

    destLibDir = os.path.join(os.getcwd(), "lib", platformLibName)

    zipDir = getZipPath(destLibDir, platformLibName)

    isBuilt = os.path.exists(zipDir)

    return not isBuilt


def tryAndDownloadBinaries(forceBuild, buildiOS):
    if forceBuild:
        return False

    # as we build both ios and ios simulator together, try and
    # download them together
    if platform.system() == "Darwin" and buildiOS:
        if not downloadBinaries(True, False):
            return False
        result = downloadBinaries(False, True)
        return result
    else:
        result = downloadBinaries(False, False)
        return result


def downloadBinaries(buildiOS, buildiOSSimulator):
    print("Trying to download pre-built binaries...")

    sdlDownloadURLWindows = f"https://github.com/snowmeltarcade/project-dependencies/releases/download/SDL_{sdlVersion}/{sdlVersion}_Windows.zip"
    sdlDownloadURLDarwin = f"https://github.com/snowmeltarcade/project-dependencies/releases/download/SDL_{sdlVersion}/{sdlVersion}_Darwin.zip"
    sdlDownloadURLiOS = f"https://github.com/snowmeltarcade/project-dependencies/releases/download/SDL_{sdlVersion}/{sdlVersion}_iOS.zip"
    sdlDownloadURLiOSSimulator = f"https://github.com/snowmeltarcade/project-dependencies/releases/download/SDL_{sdlVersion}/{sdlVersion}_iOS_Simulator.zip"
    sdlDownloadURLLinux = f"https://github.com/snowmeltarcade/project-dependencies/releases/download/SDL_{sdlVersion}/{sdlVersion}_Linux.zip"

    url = ""

    system_name = platform.system()
    if system_name == "Windows":
        url = sdlDownloadURLWindows
    elif system_name == "Darwin":
        if buildiOS:
            url = sdlDownloadURLiOS
        elif buildiOSSimulator:
            url = sdlDownloadURLiOSSimulator
        else:
            url = sdlDownloadURLDarwin
    elif system_name == "Linux":
        url = sdlDownloadURLLinux
    else:
        print(f"Unknown system name: {system_name}")
        return False

    if url == "":
        return False

    platformLibName = getPlatformLibName(buildiOS, buildiOSSimulator)

    destLibDir = os.path.join(os.getcwd(), "lib", platformLibName)
    zipDir = getZipPath(destLibDir, platformLibName)

    result = downloadBinary(url, zipDir)

    print("Finished trying.")

    return result


def downloadBinary(url, output_path):
    print(f"Trying to download url: '{url}' to path: '{output_path}'")

    cmd = [curlPath, "--create-dirs", "-Lo", f"{output_path}", f"{url}"]

    if runCmdIgnoreError(cmd):
        print(f"Downloaded binary: {url}")
        return True
    else:
        print(f"Failed to download binary: {url}")
        return False


print(f"Building SDL version {sdlVersion}...")

args = configureArguments()

if args.version is not None and len(args.version) > 0:
    sdlVersion = args.version

cwd = os.getcwd()
tempDirPath = os.path.join(cwd, "__temp")

if doesNeedBuilding(args.build_ios):
    if tryAndDownloadBinaries(args.force_build, args.build_ios):
        print("Downloaded pre-built binaries.")
    else:
        build(args.build_ios, tempDirPath)

        saveResults(args.build_ios, tempDirPath)
else:
    print("SDL is already built...")

print(f"Built SDL version {sdlVersion}.")