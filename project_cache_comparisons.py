from command_comparer import *

BASELINE_MSBUILD_EXE = Path(r'E:\projects\msbuild_2\artifacts\bin\bootstrap\net472\MSBuild\Current\Bin\MSBuild.exe')
MSBUILD_EXE = Path(r'E:\projects\msbuild\artifacts\bin\bootstrap\net472\MSBuild\Current\Bin\MSBuild.exe')
LOCAL_CACHE = Path(r"E:\CloudBuildCache")
QUICKBUILD_INSTALLATION = Path(r"E:\projects\CloudBuild\target\distrib\retail\amd64\ClientTools\Client")
TEST_REPOS_ROOT = Path(r"E:\qb_repos")

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
    f" else {{Write-Output 'Does not exist: {str(LOCAL_CACHE)}'}}",
    validation_checks=[
        Func(lambda _: not LOCAL_CACHE.is_dir(), "QB cache dir still exists")
    ]
)

MSBUILD_SUCCESSFUL_BUILD_VALIDATION = [
    Include("Build succeeded."),
    Include("0 Error(s)")
]

MSBUILD_ALL_CACHE_HITS_VALIDATION = [
    Include("Plugin result: CacheHit. Skipping project."),
    Exclude("Plugin result: CacheMiss. Building project.")
]

MSBUILD_RESTORE = ProcessCommand(
    str(MSBUILD_EXE), "/t:restore", "/m",
    validation_checks=MSBUILD_SUCCESSFUL_BUILD_VALIDATION
)

MSBUILD_COMMON_ARGS = (
    "/graph", "/m", "/clp:'verbosity=minimal;summary'", "/restore:false")

BUILD_WITH_MSBUILD = ProcessCommand(
    str(MSBUILD_EXE), *MSBUILD_COMMON_ARGS,
    validation_checks=MSBUILD_SUCCESSFUL_BUILD_VALIDATION
)

BUILD_WITH_MSBUILD_EXPECT_ALL_CACHE_HITS = BUILD_WITH_MSBUILD.add_validation_checks(
    MSBUILD_ALL_CACHE_HITS_VALIDATION)

BUILD_WITH_BASELINE_MSBUILD = ProcessCommand(
    str(BASELINE_MSBUILD_EXE), *MSBUILD_COMMON_ARGS,
    validation_checks=MSBUILD_SUCCESSFUL_BUILD_VALIDATION
)

BUILD_WITH_BASELINE_MSBUILD_EXPECT_ALL_CACHE_HITS = BUILD_WITH_BASELINE_MSBUILD.add_validation_checks(
    MSBUILD_ALL_CACHE_HITS_VALIDATION)

BUILD_WITH_QUICKBUILD = ProcessCommand(
    str(QUICKBUILD_EXE), "-notest", "-msbuildrestore:false",
    validation_checks=[
        Exclude("errors trace messages found"),
        Exclude("ERROR")
    ]
)

BUILD_WITH_QUICKBUILD_EXPECT_NO_BUILDS = BUILD_WITH_QUICKBUILD.add_validation_checks([
        Include("(100.0%) retrieved from cache (no build)"),
        Exclude("This build had cache misses"),
        Exclude("Building (cache miss)")
    ])

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
                test_command=BUILD_WITH_QUICKBUILD_EXPECT_NO_BUILDS
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_QUICKBUILD_EXPECT_NO_BUILDS
            )
        ]
    ),
    TestSuite(
        name="plugin",
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
                setup_command=Commands(MSBUILD_RESTORE, BUILD_WITH_QUICKBUILD),
                test_command=BUILD_WITH_MSBUILD_EXPECT_ALL_CACHE_HITS
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_MSBUILD_EXPECT_ALL_CACHE_HITS
            )
        ],
        environment_variables={
            "EnableQuickBuildCachePlugin": "true",
            "_CurrentQuickBuildPath": str(QUICKBUILD_INSTALLATION)
        }
    ),
    TestSuite(
        name="plugin-baseline",
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
                setup_command=Commands(MSBUILD_RESTORE, BUILD_WITH_QUICKBUILD),
                test_command=BUILD_WITH_BASELINE_MSBUILD_EXPECT_ALL_CACHE_HITS
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_BASELINE_MSBUILD_EXPECT_ALL_CACHE_HITS
            )
        ],
        environment_variables={
            "EnableQuickBuildCachePlugin": "true",
            "_CurrentQuickBuildPath": str(QUICKBUILD_INSTALLATION)
        }
    ),
    TestSuite(
        name="msb",
        tests=[
            Test(
                name="clean",
                repo_root_setup_command=CLEAN_REPOSITORY,
                setup_command=MSBUILD_RESTORE,
                test_command=BUILD_WITH_MSBUILD
            ),
            Test(
                name="incremental",
                test_command=BUILD_WITH_MSBUILD
            )
        ]
    )
]

# add msbuild to the path to make qb happy
os.environ["PATH"] = f"{str(MSBUILD_EXE.parent)}{os.pathsep}{os.environ['PATH']}"

repo_results = run_tests(REPOS, TEST_REPOS_ROOT, TEST_SUITES, repetitions=3)
write_results_to_csv(repo_results, Path("repo_results.csv"))
