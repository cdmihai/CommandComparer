from measure_repos_lib import *

BASELINE_MSBUILD_EXE = Path(
    r'E:\projects\msbuild_2\artifacts\bin\bootstrap\net472\MSBuild\Current\Bin\MSBuild.exe')
CACHE_MSBUILD_EXE = Path(
    r'E:\projects\msbuild\artifacts\bin\bootstrap\net472\MSBuild\Current\Bin\MSBuild.exe')
CACHE_INITIALIZATION_LOGGER_DLL = Path(
    r"E:\projects\CloudBuild\private\Tools\MSBuildCacheInitializationLogger\src\objd\amd64\MSBuildCacheInitializationLogger.dll")
TEST_REPOS_ROOT = Path(r"E:\qb_repos")
CACHE = Path(r"E:\CloudBuildCache")

REPOS = [
    RepoSpec("cloudbuild", "private\BuildEngine",
             "private\BuildEngine\Enlistment.Library")
]

CLEAN_REPOSITORY = ProcessCommand("git", "clean", "-xdf")
DELETE_QB_CACHE = PowershellCommand(
    f"if (Test-Path {str(CACHE)}) {{rm -recurse -force {str(CACHE)} ; Write-Output 'Deleted: {str(CACHE)}'}}" +
    f" else {{Write-Output 'Does not exist: {str(CACHE)}'}}")
MSBUILD_RESTORE = ProcessCommand(
    str(BASELINE_MSBUILD_EXE), "/t:restore", "/m", "dirs.proj")
MSBUILD_BASELINE_BUILD = ProcessCommand(
    str(BASELINE_MSBUILD_EXE), "/graph", "/m", "/clp:'verbosity=minimal;summary'", "dirs.proj")
MSBUILD_CACHE_BUILD = ProcessCommand(str(CACHE_MSBUILD_EXE), "/graph", "/m", "/p:BuildProjectReferences=false", "/restore:false",
                                     "/clp:'verbosity=minimal;summary'", f"/logger:CacheInitializationLogger,{CACHE_INITIALIZATION_LOGGER_DLL}")

TEST_SUITES = [
    TestSuite(
        name="cache",
        tests=[
            Test(
                name="clean_build_remote_cache",
                repo_root_setup_command=Commands(
                    DELETE_QB_CACHE, CLEAN_REPOSITORY),
                setup_command=MSBUILD_RESTORE,
                test_command=MSBUILD_CACHE_BUILD
            ),
            Test(
                name="clean_build_local_cache",
                repo_root_setup_command=CLEAN_REPOSITORY,
                setup_command=MSBUILD_RESTORE,
                test_command=MSBUILD_CACHE_BUILD
            ),
            Test(
                name="incremental_build",
                test_command=MSBUILD_CACHE_BUILD
            )
        ]
    ),
    TestSuite(
        name="baseline",
        tests=[
            Test(
                name="clean_build",
                repo_root_setup_command=CLEAN_REPOSITORY,
                setup_command=MSBUILD_RESTORE,
                test_command=MSBUILD_BASELINE_BUILD
            ),
            Test(
                name="incremental_build",
                test_command=MSBUILD_BASELINE_BUILD
            )
        ]
    )
]

assert BASELINE_MSBUILD_EXE.is_file()
assert CACHE_MSBUILD_EXE.is_file()
assert CACHE_INITIALIZATION_LOGGER_DLL.is_file()

repo_results = run_tests(REPOS, TEST_REPOS_ROOT, TEST_SUITES)
write_results_to_csv(repo_results, "repo_results.csv")
