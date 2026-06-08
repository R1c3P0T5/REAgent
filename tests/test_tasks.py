from __future__ import annotations

import json

import pytest

from reagent.tools.task import (
    TaskCreateTool,
    TaskDeleteTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    TaskRegistry,
)
from reagent.results import ErrorResult, ShellResult


@pytest.fixture()
def reg():
    return TaskRegistry()


@pytest.fixture()
def tools(reg, monkeypatch):
    import reagent.tools.task as mod
    monkeypatch.setattr(mod, "registry", reg)
    return {
        "create": TaskCreateTool(),
        "list": TaskListTool(),
        "get": TaskGetTool(),
        "update": TaskUpdateTool(),
        "delete": TaskDeleteTool(),
    }


def _json(result: ShellResult) -> dict | list:
    return json.loads(result.text)


def _id(result: ShellResult) -> str:
    return _json(result)["id"]


# --- create ---

def test_create_returns_pending(tools):
    result = tools["create"].run({"title": "Write tests"})
    assert isinstance(result, ShellResult)
    assert _json(result)["status"] == "pending"


def test_create_with_description(tools):
    result = tools["create"].run({"title": "Fix bug", "description": "null pointer in renderer"})
    assert _json(result)["description"] == "null pointer in renderer"


def test_create_child_task(tools):
    parent_id = _id(tools["create"].run({"title": "Parent"}))
    result = tools["create"].run({"title": "Child", "parent_id": parent_id})
    assert isinstance(result, ShellResult)
    assert _json(result)["parent_id"] == parent_id


def test_create_invalid_parent(tools):
    result = tools["create"].run({"title": "Orphan", "parent_id": "deadbeef"})
    assert isinstance(result, ErrorResult)
    assert "not found" in result.text


# --- list ---

def test_list_empty(tools):
    assert _json(tools["list"].run({})) == []


def test_list_shows_all(tools):
    tools["create"].run({"title": "A"})
    tools["create"].run({"title": "B"})
    titles = {t["title"] for t in _json(tools["list"].run({}))}
    assert titles == {"A", "B"}


def test_list_encodes_parent_id(tools):
    parent_id = _id(tools["create"].run({"title": "Root"}))
    tools["create"].run({"title": "Leaf", "parent_id": parent_id})
    tasks = {t["title"]: t for t in _json(tools["list"].run({}))}
    assert tasks["Root"]["parent_id"] is None
    assert tasks["Leaf"]["parent_id"] == parent_id


# --- get ---

def test_get_not_found(tools):
    assert isinstance(tools["get"].run({"task_id": "deadbeef"}), ErrorResult)


def test_get_returns_task_fields(tools):
    task_id = _id(tools["create"].run({"title": "My task", "description": "details"}))
    data = _json(tools["get"].run({"task_id": task_id}))
    assert data["id"] == task_id
    assert data["title"] == "My task"
    assert data["description"] == "details"
    assert data["status"] == "pending"


# --- update ---

def test_update_status(tools):
    task_id = _id(tools["create"].run({"title": "Work"}))
    result = tools["update"].run({"task_id": task_id, "status": "in_progress"})
    assert _json(result)["status"] == "in_progress"


def test_update_notes(tools):
    task_id = _id(tools["create"].run({"title": "Work"}))
    result = tools["update"].run({"task_id": task_id, "notes": "halfway done"})
    assert _json(result)["notes"] == "halfway done"


def test_update_invalid_status(tools):
    task_id = _id(tools["create"].run({"title": "Work"}))
    result = tools["update"].run({"task_id": task_id, "status": "flying"})
    assert isinstance(result, ErrorResult)
    assert "invalid status" in result.text


def test_update_not_found(tools):
    assert isinstance(tools["update"].run({"task_id": "bad", "status": "completed"}), ErrorResult)


def test_update_complete_cascades_to_descendants(tools):
    parent_id = _id(tools["create"].run({"title": "Parent"}))
    child_id = _id(tools["create"].run({"title": "Child", "parent_id": parent_id}))
    grandchild_id = _id(tools["create"].run({"title": "Grandchild", "parent_id": child_id}))
    tools["update"].run({"task_id": parent_id, "status": "completed"})
    assert _json(tools["get"].run({"task_id": child_id}))["status"] == "completed"
    assert _json(tools["get"].run({"task_id": grandchild_id}))["status"] == "completed"


def test_update_failed_cascades_to_descendants(tools):
    parent_id = _id(tools["create"].run({"title": "Parent"}))
    child_id = _id(tools["create"].run({"title": "Child", "parent_id": parent_id}))
    tools["update"].run({"task_id": parent_id, "status": "failed"})
    assert _json(tools["get"].run({"task_id": child_id}))["status"] == "failed"


def test_update_cancel_cascades_to_descendants(tools):
    parent_id = _id(tools["create"].run({"title": "Parent"}))
    child_id = _id(tools["create"].run({"title": "Child", "parent_id": parent_id}))
    tools["update"].run({"task_id": parent_id, "status": "cancelled"})
    assert _json(tools["get"].run({"task_id": child_id}))["status"] == "cancelled"


def test_update_in_progress_does_not_cascade(tools):
    parent_id = _id(tools["create"].run({"title": "Parent"}))
    child_id = _id(tools["create"].run({"title": "Child", "parent_id": parent_id}))
    tools["update"].run({"task_id": parent_id, "status": "in_progress"})
    assert _json(tools["get"].run({"task_id": child_id}))["status"] == "pending"


# --- delete ---

def test_delete_removes_task(tools):
    task_id = _id(tools["create"].run({"title": "Temp"}))
    result = tools["delete"].run({"task_id": task_id})
    assert _json(result) == {"deleted": task_id}
    assert isinstance(tools["get"].run({"task_id": task_id}), ErrorResult)


def test_delete_not_found(tools):
    assert isinstance(tools["delete"].run({"task_id": "bad"}), ErrorResult)


def test_delete_cascades_to_children(tools):
    parent_id = _id(tools["create"].run({"title": "Parent"}))
    child_id = _id(tools["create"].run({"title": "Child", "parent_id": parent_id}))
    grandchild_id = _id(tools["create"].run({"title": "Grandchild", "parent_id": child_id}))
    tools["delete"].run({"task_id": parent_id})
    assert isinstance(tools["get"].run({"task_id": child_id}), ErrorResult)
    assert isinstance(tools["get"].run({"task_id": grandchild_id}), ErrorResult)
