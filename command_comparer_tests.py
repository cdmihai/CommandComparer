import os
import unittest
import sys

import pytest

from command_comparer import *

from assertpy import assert_that  # type: ignore
from contextlib import contextmanager
from datetime import timedelta
from pyfakefs.fake_filesystem_unittest import TestCase  # type: ignore
from pyfakefs.fake_filesystem_unittest import Pause
from typing import Dict, Tuple, Any
from types import ModuleType


@contextmanager
def mock_types(mock_map: Dict[Tuple[ModuleType, str], Any]):
    original_map: Dict[Tuple[ModuleType, str], Any] = {}

    # replace types with the given mocks
    for (module, original_attribute_name), mock_object in mock_map.items():
        original_map[(module, original_attribute_name)] = getattr(module, original_attribute_name)
        setattr(module, original_attribute_name, mock_object)

    try:
        yield
    finally:
        # replace mocks with original types
        for (module, original_attribute_name), original_attribute_object in original_map.items():
            setattr(module, original_attribute_name, original_attribute_object)


class MockTest(Test):
    def run(self, repo_root: Path, working_directory: Path) -> TestResult:
        time_delta = self.test_command.mock_time_delta()  # type: ignore
        return TestResult(self.name, time_delta, None)


class MockTimeDeltaCommand(Command):
    def __init__(self, time_deltas: Sequence[timedelta] = None):
        super().__init__()

        self.time_delta_iterator = iter(()) if time_deltas is None else (x for x in time_deltas)
        self.name = str([td.total_seconds() for td in time_deltas]) if time_deltas is not None else "Mock Command"

        self._invokeCalls = 0
        self.with_working_directory_calls = 0

    def mock_time_delta(self) -> timedelta:
        td = next(self.time_delta_iterator)

        print(f"===>>> {self.name} : {td}")

        return td

    def _invoke(self):
        self._invokeCalls = self._invokeCalls + 1

    def with_working_directory(self, working_directory: Path):
        self.with_working_directory_calls = self.with_working_directory_calls + 1
        self.working_directory = working_directory

        return self


class MockException(Exception):
    pass


class ExceptionCommand(Command):
    def __init__(self, message:str):
        super().__init__()
        self.message = message

    def _invoke(self):
        raise MockException(self.message)


class Tests(TestCase):
    def setUp(self):
        self.setUpPyfakefs()

        self.test_root = Path("/PythonTests")
        self.test_root.mkdir()

    def test_ProcessCommand_calls_process(self):
        with Pause(self.fs):
            command = ProcessCommand(sys.executable, "-c", "print('foo', end='')", capture_output=True)
            assert_that(command.working_directory).is_equal_to(Path.cwd())

            command.run()

            assert_that(command.captured_output).is_equal_to(b"foo")

    def test_PowershellCommand_calls_process(self):
        with Pause(self.fs):
            command = PowershellCommand("Write-Host -NoNewline 'foobar'", capture_output=True)
            assert_that(command.working_directory).is_equal_to(Path.cwd())

            command.run()

            assert_that(command.captured_output).is_equal_to(b"foobar")

    def test_ProcessCommand_changes_working_directory(self):
        working_directory = Path("working_directory")
        working_directory.mkdir()

        command1 = ProcessCommand(sys.executable, "-c", "print('foo')", capture_output=True)
        command2 = command1.with_working_directory(working_directory)

        assert_that(command1).is_not_same_as(command2)

    def test_Test_calls_commands(self):
        test_command = MockTimeDeltaCommand()
        repo_root_setup = MockTimeDeltaCommand()
        setup_command = MockTimeDeltaCommand()

        test = Test(
            "test",
            test_command,
            repo_root_setup,
            setup_command
        )

        repo_root = Path("root")
        working_directory = Path("working directory")

        repo_root.mkdir()
        working_directory.mkdir()

        test.run(
            repo_root=repo_root,
            working_directory=working_directory
        )

        assert_that(repo_root_setup._invokeCalls).is_equal_to(1)
        assert_that(repo_root_setup.with_working_directory_calls).is_equal_to(1)
        assert_that(repo_root_setup.working_directory).is_equal_to(repo_root)

        assert_that(setup_command._invokeCalls).is_equal_to(1)
        assert_that(setup_command.with_working_directory_calls).is_equal_to(1)
        assert_that(setup_command.working_directory).is_equal_to(working_directory)

        assert_that(test_command._invokeCalls).is_equal_to(1)
        assert_that(test_command.with_working_directory_calls).is_equal_to(1)
        assert_that(test_command.working_directory).is_equal_to(working_directory)

    def test_suite_exposes_command_exception(self):
        suite = TestSuite("s", [Test("t", ExceptionCommand("foo exception"))])

        with pytest.raises(MockException) as exc_info:
            suite.run(Path.cwd(), Path.cwd())

        assert_that(exc_info.value.args).contains("foo exception")

    def test_suite_exposes_command_exception_when_environment_vars_are_set(self):
        suite = TestSuite("s", [Test("t", ExceptionCommand("foo exception"))], {"foo": "bar"})

        with pytest.raises(MockException) as exc_info:
            suite.run(Path.cwd(), Path.cwd())

        assert_that(exc_info.value.args).contains("foo exception")

    def test_suite_can_set_environment_variables(self):
        with Pause(self.fs):
            assert_that(os.environ).does_not_contain_key("foo")
            initial_environment = os.environ.copy()

            suite_result = TestSuite(
                "s",
                [Test("t", PowershellCommand("Write-Host -NoNewline $env:foo", capture_output=True))],
                {"foo": "bar"}
            ).run(Path.cwd(), Path.cwd())

            assert_that(suite_result.test_results[0].command.captured_output).is_equal_to(b'bar')
            assert_that(os.environ).is_equal_to(initial_environment)

    def test_run_tests_executes_suites_and_averages_runtimes(self):
        repo_path = self.test_root / "r1"
        repo_path.mkdir()

        repos = [
            RepoSpec(
                "r1",
                "r1s1",
                "r1s2"
            )
        ]

        test_suites = [
            TestSuite(
                "s1",
                [
                    MockTest(
                        "s1t1",
                        MockTimeDeltaCommand(
                            [
                                # mean is 3
                                timedelta(seconds=1),
                                timedelta(seconds=2),
                                timedelta(seconds=6),
                                # mean is 4
                                timedelta(seconds=1),
                                timedelta(seconds=3),
                                timedelta(seconds=8),

                            ])
                    ),
                    MockTest(
                        "s1t2",
                        MockTimeDeltaCommand(
                            [
                                # mean is 6
                                timedelta(seconds=3),
                                timedelta(seconds=5),
                                timedelta(seconds=10),
                                # mean is 5
                                timedelta(seconds=3),
                                timedelta(seconds=4),
                                timedelta(seconds=8),
                            ])
                    )
                ]
            )
        ]

        results = run_tests(repos, self.test_root, test_suites, repetitions=3)

        assert_that(results[0].name).is_equal_to(f"r1{os.sep}r1s1")
        assert_that(len(results[0].test_suite_results)).is_equal_to(1)
        assert_that(len(results[0].test_suite_results[0].test_results)).is_equal_to(2)
        assert_that(results[0].test_suite_results[0].test_results[1].name).is_equal_to("s1t2")
        assert_that(results[0].test_suite_results[0].test_results[1].time_delta.total_seconds()).is_equal_to(6)
        assert_that(results[0].test_suite_results[0].test_results[0].name).is_equal_to("s1t1")
        assert_that(results[0].test_suite_results[0].test_results[0].time_delta.total_seconds()).is_equal_to(3)

        assert_that(results[1].name).is_equal_to(f"r1{os.sep}r1s2")
        assert_that(len(results[1].test_suite_results)).is_equal_to(1)
        assert_that(len(results[1].test_suite_results[0].test_results)).is_equal_to(2)
        assert_that(results[1].test_suite_results[0].test_results[0].name).is_equal_to("s1t1")
        assert_that(results[1].test_suite_results[0].test_results[0].time_delta.total_seconds()).is_equal_to(4)
        assert_that(results[1].test_suite_results[0].test_results[1].name).is_equal_to("s1t2")
        assert_that(results[1].test_suite_results[0].test_results[1].time_delta.total_seconds()).is_equal_to(5)
