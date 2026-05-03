import requests
import time
import json
import uuid

base_urls = {
    "auth": "http://localhost:8000",
    "registry": "http://localhost:8001",
    "ingestion": "http://localhost:8002",
    "coordination": "http://localhost:8003",
    "intelligence": "http://localhost:8004",
    "analytics": "http://localhost:8005",
}

def print_step(msg):
    print(f"\n[{time.strftime('%H:%M:%S')}] {msg}")

def check_res(res, expected=200):
    if res.status_code != expected:
        print(f"FAILED (expected {expected}, got {res.status_code})")
        print(res.text)
        exit(1)
    return res.json()

# 1. Login as Admin
print_step("Logging in as admin")
res = requests.post(base_urls["auth"] + "/auth/login", json={"email": "admin@nexus.org", "password": "admin123"})
auth_data = check_res(res)
access_token = auth_data["access_token"]
tenant_id = auth_data["tenant_id"]

# Wait, admin@nexus.org has tenant_id = null. We need to pass X-Tenant-ID header.
# Let's get tenants.
print_step("Fetching tenants")
headers = {"Authorization": f"Bearer {access_token}"}
res = requests.get(base_urls["auth"] + "/auth/tenants/public")
tenants = check_res(res)
tenant_id = tenants[0]["tenant_id"] if len(tenants) > 0 else None
print(f"Using Tenant ID: {tenant_id}")
headers["X-Tenant-ID"] = tenant_id

# 2. Ingest CSV
print_step("Injecting CSV with severe need")
csv_content = """description,category,location,beneficiary_count
"Severe medical emergency, patient bleeding heavily after accident, requires first aid and transport",health,"ward-1",1"""
files = {'file': ('test_need.csv', csv_content, 'text/csv')}
res = requests.post(base_urls["ingestion"] + "/ingest/csv", headers=headers, files=files)
ingest_res = check_res(res, expected=202)
need_id = ingest_res["items"][0]["need_id"]
print(f"Created Need ID: {need_id}")

# Give the intelligence service a second to score it via event bridge
time.sleep(2)

# 3. Create Volunteer with matching skills
print_step("Registering Volunteer with Medical/First Aid skills")
vol_payload = {
    "tenant_id": tenant_id,
    "skills": ["medical", "first_aid"],
    "preferred_language": ["English"],
    "skill_proficiency": {"medical": "expert", "first_aid": "expert"},
    "max_distance_km": 15,
    "ward_id": "ward-1",
    "phone_number": "+919876543210",
    "latitude": 19.0760,
    "longitude": 72.8777
}
res = requests.post(base_urls["coordination"] + "/coordination/volunteers", headers=headers, json=vol_payload)
vol_data = check_res(res, expected=201)
volunteer_id = vol_data["volunteer_id"]
print(f"Created Volunteer ID: {volunteer_id}")

# 4. Create Task from Need
print_step("Coordinator creates Task from Need")
res = requests.post(base_urls["coordination"] + "/coordination/tasks", headers=headers, json={"need_id": need_id})
task_data = check_res(res, expected=201)
task_id = task_data["task_id"]
print(f"Created Task ID: {task_id}")

# 5. Get Matches
print_step("Coordinator getting Volunteer Matches for Task")
res = requests.get(base_urls["coordination"] + f"/coordination/tasks/{task_id}/matches", headers=headers, params={"radius_km": 15})
matches = check_res(res)
matched_volunteer = next((m for m in matches["matches"] if m["volunteer_id"] == volunteer_id), None)
print(f"Match found? {'YES' if matched_volunteer else 'NO'} (Score: {matched_volunteer['match_score'] if matched_volunteer else 'N/A'})")

# 6. Dispatch Task
print_step("Coordinator Dispatching Task to Volunteer")
res = requests.post(base_urls["coordination"] + f"/coordination/tasks/{task_id}/dispatch", headers=headers, json={"volunteer_id": volunteer_id})
check_res(res)
print("Task Dispatched")

# 7. Volunteer Accepts
print_step("Volunteer Accepts Task")
res = requests.post(base_urls["coordination"] + f"/coordination/tasks/{task_id}/accept", headers=headers, params={"volunteer_id": volunteer_id})
check_res(res)
print("Task Accepted")

# 8. Volunteer Completes
print_step("Volunteer Completes Task")
res = requests.post(base_urls["coordination"] + f"/coordination/tasks/{task_id}/complete", headers=headers, params={"volunteer_id": volunteer_id}, json={
    "outcome_status": "need_fully_met",
    "notes": "Patient stabilized and transported to hospital",
    "time_spent_minutes": 45
})
check_res(res)
print("Task Completed")

# 9. Coordinator Provides Feedback and Closes
print_step("Coordinator Closes Task with Feedback")
res = requests.post(base_urls["coordination"] + f"/coordination/tasks/{task_id}/close", headers=headers, json={
    "resolution_quality": "high",
    "volunteer_rating": 5,
    "close_notes": "Great job by volunteer"
})
check_res(res)
print("Task Closed")

# 10. Test Reject Flow
print_step("Testing Reject Flow: Creating another task")
res = requests.post(base_urls["coordination"] + "/coordination/tasks", headers=headers, json={"need_id": need_id})
task_id_2 = check_res(res, expected=201)["task_id"]

print_step("Dispatching second task to volunteer")
requests.post(base_urls["coordination"] + f"/coordination/tasks/{task_id_2}/dispatch", headers=headers, json={"volunteer_id": volunteer_id})

print_step("Volunteer Declines/Rejects Task")
res = requests.post(base_urls["coordination"] + f"/coordination/tasks/{task_id_2}/decline", headers=headers, params={"volunteer_id": volunteer_id}, json={"reason": "Currently busy with another emergency"})
check_res(res)
print("Task Declined by Volunteer successfully")

print_step("All E2E flows completed successfully!")
