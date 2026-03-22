from app import create_app
from app.models.project import ProjectManager


def test_delete_project_removes_project_directory(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    project = ProjectManager.create_project(name="待删除项目")

    app = create_app()
    client = app.test_client()

    response = client.delete(f"/api/project/{project.project_id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["project_id"] == project.project_id
    assert ProjectManager.get_project(project.project_id) is None
    assert not (tmp_path / "projects" / project.project_id).exists()

    lookup_response = client.get(f"/api/project/{project.project_id}")
    assert lookup_response.status_code == 404
