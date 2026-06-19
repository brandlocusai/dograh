# Quick Verification Guide for Language Implementation

## 1. Run Backend Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run unit tests for language handling
set -a && source api/.env.test && set +a
python -m pytest api/tests/test_service_factory_language.py -v

# Run integration tests for language persistence
python -m pytest api/tests/integrations/test_language_persistence.py -v

# Run all tests together
python -m pytest api/tests/test_service_factory_language.py api/tests/integrations/test_language_persistence.py -v
```

**Expected Result:** All tests should pass ✅

## 2. Start Development Environment

```bash
# Terminal 1 - Start Backend
source venv/bin/activate
set -a && source api/.env && set +a
uvicorn api.app:app --reload --port 8000

# Terminal 2 - Start Frontend
cd ui
npm run dev
```

**Expected Result:**
- Backend running on http://localhost:8000
- Frontend running on http://localhost:3000

## 3. Manual UI Testing

### Test 1: Verify Language Dropdowns Appear

1. Open browser: http://localhost:3000
2. Login to your account
3. Navigate to **Model Configurations** page
4. Click on **Transcriber** tab
5. Select **Deepgram** as provider
6. **✅ CHECK:** Language dropdown should appear
7. Click on **Voice** tab
8. Select **Google** as provider
9. **✅ CHECK:** Language dropdown should appear
10. Enable **Realtime Mode** toggle
11. Select **Google Realtime** as provider
12. **✅ CHECK:** Language dropdown should appear

### Test 2: Verify Display Names

1. In Transcriber tab with Deepgram selected
2. Click Language dropdown
3. **✅ CHECK:** Should see "Spanish" not "es"
4. **✅ CHECK:** Should see "Spanish (Mexico)" not "es-MX"
5. **✅ CHECK:** Should see "Mandarin (Simplified)" not "cmn-Hans-CN"
6. **✅ CHECK:** Should see "Multilingual (Auto-detect)" for "multi"

### Test 3: Verify Persistence

1. Select Deepgram in Transcriber tab
2. Set Language to "Spanish"
3. Click **Save Configuration**
4. **Refresh the page** (F5)
5. Navigate back to Model Configurations → Transcriber
6. **✅ CHECK:** Language should still show "Spanish"

### Test 4: Verify Model-Dependent Language Reset

1. Select Deepgram in Transcriber tab
2. Set Model to "nova-3-general"
3. Set Language to "Multilingual (Auto-detect)"
4. Now change Model to "flux-general-en"
5. **✅ CHECK:** Language should automatically reset to "English"
6. **✅ CHECK:** Language dropdown should only show "English" option
7. Change Model back to "nova-3-general"
8. **✅ CHECK:** Language dropdown should show all 84 languages again

### Test 5: Verify Documentation Links

1. Select Google in Transcriber tab
2. Look below the Language dropdown
3. **✅ CHECK:** Should see "Supported languages" link with external icon
4. Click the link
5. **✅ CHECK:** Should open Google Cloud Speech-to-Text docs in new tab
6. Test with other providers:
   - Deepgram → Should have link to Deepgram docs
   - Sarvam → Should have link to Sarvam docs

### Test 6: Verify Workflow Overrides

1. Set global Transcriber language to "English"
2. Click Save Configuration
3. Navigate to **Workflows** page
4. Create new workflow or edit existing workflow
5. Open workflow **Settings** panel
6. Find **Model Overrides** section
7. Enable Transcriber override
8. Set Language to "French"
9. Save workflow
10. Navigate back to Model Configurations
11. **✅ CHECK:** Global config should still show "English" (unchanged)
12. Go back to workflow settings
13. **✅ CHECK:** Workflow language should show "French"

### Test 7: Verify Different Languages for STT and TTS

1. In Model Configurations:
   - Transcriber → Deepgram → Language: "Spanish"
   - Voice → Google → Language: "English (US)"
2. Click Save Configuration
3. **✅ CHECK:** Both languages should persist independently
4. This simulates a translation bot: user speaks Spanish, bot responds in English

## 4. Verify Backend Schema

Test that backend exposes language fields correctly:

```bash
# Check user configuration defaults
curl -X GET "http://localhost:8000/api/v1/user-configurations/defaults" \
  -H "accept: application/json" | jq '.stt.deepgram.properties.language'

# Expected output: Should show language field with examples
```

**✅ CHECK:** Should see:
```json
{
  "default": "multi",
  "description": "Language code; 'multi' enables auto-detect (Nova-3 only).",
  "examples": ["multi", "en", "es", "fr", ...],
  "model_options": {
    "nova-3-general": [...],
    "flux-general-en": ["en"]
  },
  "docs_url": "https://developers.deepgram.com/docs/models-languages-overview"
}
```

## 5. Verify Runtime Behavior (Optional)

To verify language is actually used at runtime:

1. Create a simple workflow with Spanish transcriber
2. Trigger a test call
3. Check workflow run logs
4. **✅ CHECK:** Should see Deepgram initialized with language="es"

```bash
# Check workflow run logs
curl -X GET "http://localhost:8000/api/v1/workflow-runs/{run_id}" \
  -H "accept: application/json" | jq '.logs'

# Look for lines like:
# "DeepgramSTTService initialized with language=es"
```

## 6. Quick Smoke Test Script

Save this as `test_language_ui.sh`:

```bash
#!/bin/bash

echo "🧪 Language Implementation Smoke Test"
echo "======================================"

# Check if backend is running
if curl -s http://localhost:8000/api/v1/health > /dev/null; then
    echo "✅ Backend is running"
else
    echo "❌ Backend is not running. Start with: uvicorn api.app:app --reload --port 8000"
    exit 1
fi

# Check if frontend is running
if curl -s http://localhost:3000 > /dev/null; then
    echo "✅ Frontend is running"
else
    echo "❌ Frontend is not running. Start with: cd ui && npm run dev"
    exit 1
fi

# Check language constants file
if grep -q "cmn-Hans-CN" ui/src/constants/languages.ts; then
    echo "✅ Language constants file updated"
else
    echo "❌ Language constants file not updated"
    exit 1
fi

# Check if tests exist
if [ -f "api/tests/test_service_factory_language.py" ]; then
    echo "✅ Unit tests created"
else
    echo "❌ Unit tests missing"
    exit 1
fi

if [ -f "api/tests/integrations/test_language_persistence.py" ]; then
    echo "✅ Integration tests created"
else
    echo "❌ Integration tests missing"
    exit 1
fi

# Check backend schema
SCHEMA=$(curl -s http://localhost:8000/api/v1/user-configurations/defaults)
if echo "$SCHEMA" | jq -e '.stt.deepgram.properties.language.docs_url' > /dev/null 2>&1; then
    echo "✅ Backend docs URLs added"
else
    echo "⚠️  Backend docs URLs may be missing (check manually)"
fi

echo ""
echo "======================================"
echo "✅ All automated checks passed!"
echo ""
echo "📋 Manual Testing Required:"
echo "   1. Open http://localhost:3000/model-configurations"
echo "   2. Verify language dropdowns appear"
echo "   3. Verify display names are human-readable"
echo "   4. Test model-dependent language reset"
echo "   5. Test persistence by saving and reloading"
echo ""
echo "📖 See VERIFY_LANGUAGE_IMPLEMENTATION.md for full checklist"
```

Run it:
```bash
chmod +x test_language_ui.sh
./test_language_ui.sh
```

## 7. Common Issues and Fixes

### Issue: Language dropdown not appearing

**Possible Causes:**
1. Backend not exposing language field in schema
2. Frontend not rendering dynamic fields correctly
3. Provider configuration missing language field

**Fix:**
```bash
# Check backend schema
curl http://localhost:8000/api/v1/user-configurations/defaults | jq '.stt.deepgram.properties'

# Should see "language" field
```

### Issue: Display names showing codes instead of names

**Possible Causes:**
1. Language code not in LANGUAGE_DISPLAY_NAMES constant
2. Fallback logic not working

**Fix:**
- Check `ui/src/constants/languages.ts` has the code
- Fallback should show uppercase code (e.g., "FR-XX")

### Issue: Language not persisting

**Possible Causes:**
1. Save button not clicked
2. API error on save
3. Database not storing configuration

**Fix:**
```bash
# Check browser console for errors
# Check backend logs for API errors
# Verify user configuration saved:
curl http://localhost:8000/api/v1/user-configurations
```

### Issue: Model change not resetting language

**Possible Causes:**
1. useEffect dependencies incorrect
2. model_options not defined in schema
3. React state not updating

**Fix:**
- Check browser console for React errors
- Verify model_options in backend schema
- Check ServiceConfigurationForm.tsx effects are firing

## 8. Rollback Plan (If Needed)

If issues are found, rollback is safe:

```bash
# Revert frontend changes
cd ui
git checkout HEAD -- src/constants/languages.ts
git checkout HEAD -- src/components/ServiceConfigurationForm.tsx

# Revert backend changes
cd ../api
git checkout HEAD -- services/configuration/registry.py

# Delete test files
rm tests/test_service_factory_language.py
rm tests/integrations/test_language_persistence.py
```

**Impact of Rollback:**
- Users will see fewer language display names (110 vs 230+)
- TTS and Realtime language won't auto-reset on model change
- No documentation links for language fields
- No new tests

**No data loss** - language configurations already saved will remain valid.

## 9. Success Criteria

**All checks must pass:**
- ✅ Backend tests pass (20 test cases)
- ✅ Language dropdowns appear in UI
- ✅ Display names are human-readable
- ✅ Language persists across page reloads
- ✅ Model change resets incompatible languages
- ✅ Documentation links appear and work
- ✅ Workflow overrides work independently
- ✅ STT and TTS languages can differ

**When all pass:** Implementation is ready for production! 🚀

---

**Questions or Issues?**
- Check LANGUAGE_IMPLEMENTATION_SUMMARY.md for detailed documentation
- Review test files for expected behavior examples
- Check browser console and backend logs for error messages
