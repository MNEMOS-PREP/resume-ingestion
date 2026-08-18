import uuid


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "module": "M01"}

def test_ingest_resume(client):
    candidate_id = str(uuid.uuid4())
    # Post resume text
    res = client.post(
        "/v1/resumes/ingest",
        json={
            "candidate_id": candidate_id,
            "raw_text": "Experienced developer in Dynamic Programming, recursion, and hashing algorithms."
        }
    )
    assert res.status_code == 201
    data = res.json()
    assert data["candidate_id"] == candidate_id
    assert "Dynamic Programming" in data["parsed_skills"]
    assert "Recursion" in data["parsed_skills"]

    # Test get resume by id
    resume_id = data["id"]
    res_get = client.get(f"/v1/resumes/{resume_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == resume_id

    # Test get resumes by candidate
    res_candidate = client.get(f"/v1/resumes/candidate/{candidate_id}")
    assert res_candidate.status_code == 200
    assert len(res_candidate.json()) == 1
