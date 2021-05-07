from command_comparer import *

BASELINE_MSBUILD_EXE = Path(
    r'E:\projects\msbuild_2\artifacts\bin\bootstrap\net472\MSBuild\Current\Bin\MSBuild.exe')
MSBUILD_EXE = Path(
    r'E:\projects\msbuild\artifacts\bin\bootstrap\net472\MSBuild\Current\Bin\MSBuild.exe')
TEST_REPOS_ROOT = Path(r"E:\qb_repos")
LOCAL_CACHE = Path(r"E:\CloudBuildCache")
QUICKBUILD_INSTALLATION = Path(
    r"C:/Users/micodoba/AppData/Local/CloudBuild/quickbuild")

assert QUICKBUILD_INSTALLATION.is_dir()

quickbuilds_sorted_by_creation_time = sorted(
    QUICKBUILD_INSTALLATION.glob(r"**\quickbuild.exe"),
    key=lambda p: p.stat().st_ctime)
QUICKBUILD_EXE = quickbuilds_sorted_by_creation_time[-1]

assert QUICKBUILD_EXE.is_file()
assert MSBUILD_EXE.is_file()
assert BASELINE_MSBUILD_EXE.is_file()
assert TEST_REPOS_ROOT.is_dir()

CLEAN_REPOSITORY = ProcessCommand("git", "clean", "-xdf")

DELETE_QB_CACHE = PowershellCommand(
    f"if (Test-Path {str(LOCAL_CACHE)})"
    f" {{rm -recurse -force {str(LOCAL_CACHE)} ; Write-Output 'Deleted: {str(LOCAL_CACHE)}'}}"
    f" else {{Write-Output 'Does not exist: {str(LOCAL_CACHE)}'}}")

MSBUILD_RESTORE = ProcessCommand(
    str(MSBUILD_EXE), "/t:restore", "/m")

MSBUILD_COMMON_ARGS = (
    "/graph", "/m", "/clp:'verbosity=minimal;summary'", "/restore:false")

BUILD_WITH_MSBUILD = ProcessCommand(
    str(MSBUILD_EXE), *MSBUILD_COMMON_ARGS)

BUILD_WITH_BASELINE_MSBUILD = ProcessCommand(
    str(BASELINE_MSBUILD_EXE), *MSBUILD_COMMON_ARGS)

BUILD_WITH_QUICKBUILD = ProcessCommand(
    str(QUICKBUILD_EXE), "-notest", "-msbuildrestore:false")

REPOS = [
    RepoSpec(
        "CloudBuild",
        r"private\BuildEngine\Enlistment.Library",  # 32 build nodes
        r"private\BuildEngine\BuildClient"  # 104 build nodes
    )
]

TEST_SUITES = [
    TestSuite(
        name="qb",
        tests=[
            Test(
                name="clean_remote_cache",
                repo_root_setup_command=Commands(
                    DELETE_QB_CACHE, CLEAN_REPOSITORY),
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_QUICKBUILD
            ),
            Test(
                name="clean_local_cache",
                repo_root_setup_command=CLEAN_REPOSITORY,
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_QUICKBUILD
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_QUICKBUILD
            )
        ]
    ),
    TestSuite(
        name="msb-plugin",
        tests=[
            Test(
                name="clean-remote-cache",
                repo_root_setup_command=Commands(
                    DELETE_QB_CACHE, CLEAN_REPOSITORY),
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_MSBUILD
            ),
            Test(
                name="clean-local-cache",
                repo_root_setup_command=CLEAN_REPOSITORY,
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_MSBUILD
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_MSBUILD
            )
        ],
        environment_variables={
            "EnableQuickBuildCachePlugin": "true"
        }
    ),
    TestSuite(
        name="msb-plugin-baseline",
        tests=[
            Test(
                name="clean-remote-cache",
                repo_root_setup_command=Commands(
                    DELETE_QB_CACHE, CLEAN_REPOSITORY),
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_BASELINE_MSBUILD
            ),
            Test(
                name="clean-local-cache",
                repo_root_setup_command=CLEAN_REPOSITORY,
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_BASELINE_MSBUILD
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_BASELINE_MSBUILD
            )
        ],
        environment_variables={
            "EnableQuickBuildCachePlugin": "true"
        }
    ),
    TestSuite(
        name="msb",
        tests=[
            Test(
                name="clean",
                repo_root_setup_command=CLEAN_REPOSITORY,
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_BASELINE_MSBUILD
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_BASELINE_MSBUILD
            )
        ]
    )
]

# add msbuild to the path to make qb happy
os.environ["PATH"] = f"{str(MSBUILD_EXE.parent)}{os.pathsep}{os.environ['PATH']}"

repo_results = run_tests(REPOS, TEST_REPOS_ROOT, TEST_SUITES, repetitions=3)
write_results_to_csv(repo_results, Path("repo_results.csv"))
