import sys
from pathlib import Path

import pytest

from scripts.check_commit_msg import (
    MAX_HEADER_LENGTH,
    MAX_SUBJECT_LENGTH,
    _ALLOWED_TYPES,
    validate_commit_message,
)
from scripts.check_commit_msg import main as cli_main


# —— Valid messages ————————————————————————————————————————————————————————————
@pytest.mark.parametrize(
    "message",
    [
        "feat(frontend): add login form\n\nbody\n",
        "fix: remove nil pointer crash\n",
        "docs: update readme to reflect new api\n",
        "refactor(api): split handler\n",
        "perf!: reduce allocations\n",
        "feat(parser)!: support breaking syntax\n",
        # scope with hyphens, underscores, digits
        "feat(my-module): add thing\n",
        "feat(v2_api): add endpoint\n",
        "fix(auth-v2): patch token refresh\n",
        # first word with hyphen
        "feat: re-add deprecated helper\n",
        # single-letter first word
        "feat: a new flag\n",
        # short past-tense-looking words that are NOT flagged (len <= 4)
        "feat: add bed support\n",
        "feat: add red alerts\n",
        # message without trailing newline
        "fix: correct off-by-one",
        # multiline body
        "feat: add oauth support\n\nLong description here.\n\nCloses #42\n",
    ],
)
def test_valid_messages(message: str) -> None:
    result = validate_commit_message(message)
    assert result["ok"], result


@pytest.mark.parametrize("commit_type", _ALLOWED_TYPES)
def test_all_allowed_types_are_accepted(commit_type: str) -> None:
    result = validate_commit_message(f"{commit_type}: add thing\n")
    assert result["ok"], result


# —— Autosquash prefixes ———————————————————————————————————————————————————————
@pytest.mark.parametrize(
    "message",
    [
        "fixup! feat: add thing\n",
        "squash! fix(core): remove crash\n",
        # autosquash wrapping a breaking change
        "fixup! perf!: reduce allocations\n",
    ],
)
def test_autosquash_prefixes_are_allowed(message: str) -> None:
    result = validate_commit_message(message)
    assert result["ok"], result


# —— Merge / Revert commits ————————————————————————————————————————————————————
@pytest.mark.parametrize(
    "message",
    [
        "Merge branch 'main' into feature\n",
        'Revert "feat: add broken change"\n',
        "Merge pull request #123 from org/branch\n",
    ],
)
def test_merge_and_revert_commits_are_allowed(message: str) -> None:
    result = validate_commit_message(message)
    assert result["ok"], result


# —— AI co-author signature ———————————————————————————————————————————————————
@pytest.mark.parametrize(
    "message",
    [
        "feat: add thing\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n",
        "fix: patch bug\n\nco-authored-by: claude opus 4.7 <noreply@anthropic.com>\n",
        "Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>\nfeat: add thing\n",
    ],
)
def test_anthropic_coauthor_signature_is_rejected(message: str) -> None:
    result = validate_commit_message(message)
    assert not result["ok"], result
    assert any("AI co-author" in err for err in result["errors"]), result


# —— Empty / malformed messages ————————————————————————————————————————————————
def test_completely_empty_message_is_rejected() -> None:
    result = validate_commit_message("")
    assert not result["ok"]
    assert any("must not be empty" in err for err in result["errors"])


def test_only_newline_is_rejected() -> None:
    result = validate_commit_message("\n")
    assert not result["ok"]
    assert any("must follow" in err for err in result["errors"])


# —— Invalid messages ——————————————————————————————————————————————————————————
@pytest.mark.parametrize(
    "message, expected_substring",
    [
        # wrong format entirely
        ("just a plain sentence\n", "must follow"),
        # unknown type
        ("foo: add thing\n", "Commit type 'foo'"),
        # uppercase type
        ("Feat: add thing\n", "must follow"),
        # empty subject (only spaces after colon)
        ("feat:    \n", "must not be empty"),
        # subject starts with uppercase
        ("feat: Added thing\n", "must start with a lowercase imperative verb"),
        # past tense (>4 chars ending in "ed")
        ("feat: added thing\n", "imperative mood"),
        ("feat: removed old handler\n", "imperative mood"),
        # present progressive (>5 chars ending in "ing")
        ("feat: adding thing\n", "imperative mood"),
        ("feat: refactoring handler\n", "imperative mood"),
        # trailing punctuation
        ("feat: add thing.\n", "must not end with punctuation"),
        ("feat: add thing!\n", "must not end with punctuation"),
        ("feat: add thing?\n", "must not end with punctuation"),
        # subject starts with digit
        ("feat: 5 things added\n", "must start with a lowercase imperative verb"),
        # invalid scope (uppercase)
        ("feat(MyModule): add thing\n", "must follow"),
    ],
)
def test_invalid_messages(message: str, expected_substring: str) -> None:
    result = validate_commit_message(message)
    assert not result["ok"], result
    assert any(expected_substring in err for err in result["errors"]), result


# —— Vague update subjects ————————————————————————————————————————————————————
@pytest.mark.parametrize(
    "subject",
    [
        "update readme",
        "update README.md",
        "Update dependencies",
        "UPDATE changelog",
    ],
)
def test_vague_update_subject_is_rejected(subject: str) -> None:
    result = validate_commit_message(f"chore: {subject}\n")
    assert not result["ok"], result
    assert any("auto-generated" in err for err in result["errors"]), result


@pytest.mark.parametrize(
    "subject",
    [
        "update readme to reflect new api",
        "update npm dependencies for security patch",
    ],
)
def test_specific_update_subject_is_accepted(subject: str) -> None:
    result = validate_commit_message(f"chore: {subject}\n")
    assert result["ok"], result


# —— Vague subjects ————————————————————————————————————————————————————————————
@pytest.mark.parametrize(
    "subject",
    [
        "updates",
        "  updates  ",
        "UPDATES",
        "misc   changes",
        "Stuff",
        "Fixes",
    ],
)
def test_vague_subject_is_rejected(subject: str) -> None:
    result = validate_commit_message(f"feat: {subject}\n")
    assert not result["ok"], result
    assert any("too vague" in err for err in result["errors"]), result


@pytest.mark.parametrize(
    "subject",
    [
        # vague word as part of a longer, specific phrase is fine
        "add updates endpoint",
        "fix stuff in auth module",
    ],
)
def test_vague_word_in_specific_phrase_is_accepted(subject: str) -> None:
    result = validate_commit_message(f"feat: {subject}\n")
    assert result["ok"], result


# —— Length limits —————————————————————————————————————————————————————————————
def test_subject_at_exact_limit_is_accepted() -> None:
    # "add " = 4 chars; pad to exactly MAX_SUBJECT_LENGTH
    subject = "add " + "x" * (MAX_SUBJECT_LENGTH - 4)
    assert len(subject) == MAX_SUBJECT_LENGTH
    result = validate_commit_message(f"feat: {subject}\n")
    assert result["ok"], result


def test_subject_one_over_limit_is_rejected() -> None:
    subject = "add " + "x" * (MAX_SUBJECT_LENGTH - 4 + 1)
    assert len(subject) == MAX_SUBJECT_LENGTH + 1
    result = validate_commit_message(f"feat: {subject}\n")
    assert not result["ok"]
    assert any("subject must be at most" in err for err in result["errors"])


def test_header_at_exact_limit_is_accepted() -> None:
    # Use a long scope so the prefix is 28 chars, leaving room for a 72-char
    # subject that is exactly at MAX_SUBJECT_LENGTH:
    #   "feat(this-is-a-long-scope): " = 28 chars
    #   28 + 72 = 100 = MAX_HEADER_LENGTH
    prefix = "feat(this-is-a-long-scope): "
    subject = "add " + "x" * (MAX_SUBJECT_LENGTH - 4)
    header = prefix + subject
    assert len(header) == MAX_HEADER_LENGTH
    assert len(subject) == MAX_SUBJECT_LENGTH
    result = validate_commit_message(header + "\n")
    assert result["ok"], result


def test_header_one_over_limit_is_rejected() -> None:
    subject = "add " + "x" * (MAX_HEADER_LENGTH - 6 - 4 + 1)
    result = validate_commit_message(f"feat: {subject}\n")
    assert not result["ok"]
    assert any("header must be at most" in err for err in result["errors"])


# —— Multiple simultaneous errors ——————————————————————————————————————————————
def test_multiple_errors_are_accumulated() -> None:
    # Long subject + trailing punctuation → 2 errors, not just 1
    long_subject = "add " + "x" * (MAX_SUBJECT_LENGTH - 4 + 1)
    message = f"feat: {long_subject}.\n"
    result = validate_commit_message(message)
    assert not result["ok"]
    assert len(result["errors"]) >= 2
    assert any("subject must be at most" in err for err in result["errors"])
    assert any("must not end with punctuation" in err for err in result["errors"])


# —— CLI entrypoint ————————————————————————————————————————————————————————————
def test_cli_returns_0_for_valid_message(tmp_path: Path) -> None:
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: add login form\n", encoding="utf-8")
    assert cli_main([sys.argv[0], str(msg_file)]) == 0


def test_cli_returns_1_for_invalid_message(tmp_path: Path) -> None:
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("badformat\n", encoding="utf-8")
    assert cli_main([sys.argv[0], str(msg_file)]) == 1


def test_cli_returns_1_for_wrong_number_of_args() -> None:
    assert cli_main([sys.argv[0]]) == 1
    assert cli_main([sys.argv[0], "a", "b"]) == 1
