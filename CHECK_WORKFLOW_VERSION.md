# How to Check if Your Workflow Changes Are Saved

## Method 1: Check via UI

1. Edit your workflow (change a prompt)
2. Click **Save**
3. **Refresh the page** (Ctrl+R or Cmd+R)
4. Open the workflow again
5. **Do you see your changes?**
   - YES → Changes are saved, you need a NEW run to test them
   - NO → Changes weren't saved, save again

## Method 2: Check via API

```bash
# Get workflow details
curl -X GET "http://localhost:8000/api/v1/workflows/{workflow_id}" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Check the response - look for version_status
{
  "id": 123,
  "name": "My Workflow",
  "version_status": "draft",  # ← Should say "draft" after editing
  "workflow_definition": { ... }
}
```

## Method 3: Check Database Directly

```sql
-- Check if draft exists for your workflow
SELECT
    w.id as workflow_id,
    w.name as workflow_name,
    wd.id as definition_id,
    wd.status,
    wd.version_number,
    wd.created_at
FROM workflows w
LEFT JOIN workflow_definitions wd ON wd.workflow_id = w.id
WHERE w.id = YOUR_WORKFLOW_ID
ORDER BY wd.created_at DESC
LIMIT 5;

-- You should see:
-- status = 'draft' (most recent) ← Your edits
-- status = 'published' (older)   ← Previous version
```

## Common Issues

### Issue 1: Changes Not Showing After Edit

**Cause:** UI didn't save the draft

**Fix:**
1. Make your edit
2. Look for a **"Save" button** in the UI
3. Click it and wait for confirmation
4. Check if there's an **auto-save indicator**

### Issue 2: Old Version Still Running

**Cause:** Using an existing run (which has a pinned snapshot)

**Fix:**
1. **Close the current call/test window**
2. **Start a completely NEW test** from the workflow page
3. The new run will use your latest draft

### Issue 3: Draft Not Being Used

**Cause:** Run creation with `use_draft=False` (shouldn't happen in test mode)

**Fix:** Check backend logs when starting a run:
```bash
grep "create_workflow_run" logs/latest/api.log
```

Look for `use_draft=True` in the logs.

## Best Practice Workflow

```
1. Edit workflow → Change prompt/settings
2. Click "Save" → Creates/updates DRAFT
3. Close any existing test windows
4. Click "Test" or "Start New Call" → Creates NEW run with latest DRAFT
5. Test your changes
```

## If Nothing Works

Try this debugging sequence:

```bash
# 1. Check if draft was created
curl -X GET "http://localhost:8000/api/v1/workflows/{workflow_id}" \
  -H "Authorization: Bearer YOUR_TOKEN" | grep version_status

# 2. Create a new run explicitly
curl -X POST "http://localhost:8000/api/v1/workflows/{workflow_id}/runs" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Run","mode":"webrtc"}'

# 3. Check the run's definition_id
curl -X GET "http://localhost:8000/api/v1/workflows/{workflow_id}/runs/{run_id}" \
  -H "Authorization: Bearer YOUR_TOKEN" | grep definition_id

# 4. Verify that definition has your changes
curl -X GET "http://localhost:8000/api/v1/workflows/{workflow_id}/versions" \
  -H "Authorization: Bearer YOUR_TOKEN"
```
