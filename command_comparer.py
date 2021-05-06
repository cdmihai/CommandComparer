import copy
import csv
import os
import subprocess
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from timeit import timeit
from typing import Tuple, Sequence, Callable, Optional


def _lazy_repr(self):
    return self.__str__()


DISPLAY_WIDTH = 120


class RepoSpec:
    def __init__(self, name: str, *sub_directories: str):
        self.name = name
        self.sub_directories = tuple(Path(sub_directory)
                                     for sub_directory in sub_directories)

    def with_base_root(self, base_root: Path):
        return RootedRepo(base_root, self)

    def __str__(self):
        return f'{self.name}, {self.sub_directories}'

    def __repr__(self):
        return _lazy_repr(self)


class RootedRepo:
    def __init__(self, root: Path, repo: RepoSpec):
        self.repo_spec = repo
        self.root = root.joinpath(repo.name).resolve(strict=True)
        self.sub_directories = tuple(
            self.root / relative_sub_directory for relative_sub_directory in repo.sub_directories)

    def __str__(self):
        return f'{self.root.parent}, {self.root.name}, {[sub_dir.relative_to(self.root) for sub_dir in self.sub_directories]}'

    def __repr__(self):
        return _lazy_repr(self)


class Command(ABC):
    def __init__(self):
        self.working_directory = Path.cwd()

    def run(self):
        command_representation = f'{self.working_directory} > "{str(self)}"'

        print(command_representation)

        saved_cwd = Path.cwd()

        try:
            os.chdir(self.working_directory)
            self._invoke()
        except subprocess.CalledProcessError as e:
            print("\n[FAILED COMMAND]\n" + command_representation)
            raise e
        finally:
            os.chdir(saved_cwd)

    @abstractmethod
    def _invoke(self):
        ...

    def with_working_directory(self, working_directory: Path):
        clone = copy.deepcopy(self)
        clone.working_directory = working_directory

        return clone


class NullCommand(Command):
    def run(self):
        ...

    def _invoke(self):
        ...


class Commands(Command):
    def __init__(self, *args: Command):
        super().__init__()
        self.commands = copy.deepcopy(args)

    def _invoke(self):
        for command in self.commands:
            command.run()

    def with_working_directory(self, working_directory: Path):
        self.commands = tuple(command.with_working_directory(
            working_directory) for command in self.commands)

        return self

    def __str__(self):
        return f"Composite({len(self.commands)})"


class ProcessCommand(Command):
    def __init__(self, *args: str, capture_output=False):
        super().__init__()
        self.args = copy.copy(args)
        self.capture_output = capture_output

    def _invoke(self):
        completed_process = subprocess.run(
            self.args,
            check=True,
            capture_output=self.capture_output
        )

        self.captured_output = completed_process.stdout if self.capture_output else None

        assert completed_process.returncode == 0

    def __str__(self):
        return " ".join(self.args)


class PowershellCommand(ProcessCommand):
    def __init__(self, *args: str, capture_output=False):
        super().__init__("powershell", "-nologo", "-noprofile",
                         "-noninteractive", "-c", *args, capture_output=capture_output)


@dataclass(frozen=True)
class TestResult:
    name: str
    time_delta: timedelta
    # todo: don't make it optional and implement all scenarios that pass None
    command: Optional[Command]


@dataclass(frozen=True)
class Test:
    name: str
    test_command: Command
    repo_root_setup_command: Command = field(default=NullCommand())
    setup_command: Command = field(default=NullCommand())

    def run(self, repo_root: Path, working_directory: Path) -> TestResult:
        print(self.name.center(DISPLAY_WIDTH, "_"))

        try:
            self.repo_root_setup_command.with_working_directory(repo_root).run()
            self.setup_command.with_working_directory(working_directory).run()

            test_command = self.test_command.with_working_directory(
                working_directory)

            runtime_in_seconds = timeit(lambda: test_command.run(), number=1)

            return TestResult(self.name, (timedelta(seconds=runtime_in_seconds)), test_command)
        except Exception:
            print(f"\n[Failed test] {self.name}")
            raise


@dataclass(frozen=True)
class TestSuiteResult:
    name: str
    test_results: Tuple[TestResult, ...]


@dataclass(frozen=True)
class TestSuite:
    name: str
    tests: Sequence[Test]
    environment_variables: Mapping[str, str] = os.environ

    def run(self, repo_root: Path, working_directory: Path) -> TestSuiteResult:
        print()
        print(self.name.center(DISPLAY_WIDTH, "="))

        with environment_variables(**self.environment_variables):
            try:
                test_results = [test.run(repo_root, working_directory)
                                for test in self.tests]

                return TestSuiteResult(self.name, tuple(test_results))
            except Exception:
                print(f"\n[Failed TestSuite] {self.name}")
                print()
                raise


@dataclass(frozen=True)
class RepoResults:
    name: str
    test_suite_results: Tuple[TestSuiteResult, ...]


@contextmanager
def environment_variables(**kwargs):
    original_environment = os.environ.copy()
    try:
        os.environ |= kwargs
        yield
    finally:
        os.environ.clear()
        os.environ |= original_environment


def test_suite_repeater(test_suite_runner: Callable[[], TestSuiteResult], repetitions: int) -> TestSuiteResult:
    """
    Run the test suite multiple times and merge the multiple TestSuiteResults back into a single TestSuiteResult
    """

    def mergeTestResults(test_results: tuple[str, Sequence[TestResult]]) -> TestResult:
        name, tests = test_results

        assert all(name == test.name for test in tests)

        average_time = sum((test.time_delta for test in tests),
                           timedelta(0)) / repetitions

        return TestResult(name, average_time, None)

    test_results_per_name = defaultdict(list)
    test_suite_name = None

    for repetition in range(repetitions):
        try:
            print()
            print(f"Repetition {repetition}".center(DISPLAY_WIDTH, "+"))

            test_suite_result: TestSuiteResult = test_suite_runner()

            assert test_suite_name is None or test_suite_name == test_suite_result.name
            test_suite_name = test_suite_result.name

            for test_result in test_suite_result.test_results:
                test_results_per_name[test_result.name].append(test_result)

        except Exception:
            print(f"\n[Failed Repetition] {repetition}")
            print()
            raise

    assert test_suite_name is not None
    assert all(len(test_results) ==
               repetitions for test_results in test_results_per_name.values())

    return TestSuiteResult(test_suite_name, tuple(mergeTestResults(test_results) for test_results in test_results_per_name.items()))


def run_tests(repos: Sequence[RepoSpec], repos_root: Path, test_suites: Sequence[TestSuite], repetitions: int = 1) -> Sequence[RepoResults]:
    assert repos_root.exists() and repos_root.is_dir()
    assert len(repos) > 0
    assert len(test_suites) > 0

    rooted_repos = [repo.with_base_root(repos_root) for repo in repos]

    repo_results = []

    for repo in rooted_repos:
        for repo_subdir in repo.sub_directories:
            sub_dir_pretty_name = str(repo_subdir.relative_to(repos_root))

            print("".center(DISPLAY_WIDTH, "▇"))
            print(sub_dir_pretty_name.center(DISPLAY_WIDTH, "▇"))
            print("".center(DISPLAY_WIDTH, "▇"))

            test_suite_results = []
            for test_suite in test_suites:
                result = test_suite_repeater(lambda: test_suite.run(
                    repo.root, repo_subdir), repetitions)
                test_suite_results.append(result)

            repo_results.append(RepoResults(
                sub_dir_pretty_name, tuple(test_suite_results)))

    assert len(repo_results) > 0

    return repo_results


def write_results_to_csv(repo_results: Sequence[RepoResults], results_file: os.PathLike):
    """
    Prints multiple RepoResults to csv file.

    Each line contains the test results for one repo subdirectory.
    Each column represents the test results of a single test across all repo subdirectories.

    The layout is as follows:

    repo                 | <test suite name>_<test name> | ...
    <repo name>_<subdir> | time in seconds               | ...  
    """

    header = ["repo"] + [f"{test_suite_result.name}_{test_result.name}"
                         for test_suite_result in repo_results[0].test_suite_results
                         for test_result in test_suite_result.test_results]

    # each line has the results for one repo
    rows = [[repo_result.name] + [str(test_result.time_delta.total_seconds())
                                  for test_suite_result in repo_result.test_suite_results
                                  for test_result in test_suite_result.test_results]
            for repo_result in repo_results]

    results_file_path = Path(results_file)
    results_file_path.resolve()

    with open(results_file_path, 'w', newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"Wrote results to: {results_file_path}")
