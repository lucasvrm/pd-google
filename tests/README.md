# Tests Documentation

This directory contains the test suite for the pd-google project.

## Test Files

### Unit and Integration Tests

1. **test_mock_drive.py**
   - Tests for the mock Google Drive service
   - Runs with `USE_MOCK_DRIVE=true`

2. **test_hierarchy.py**
   - Tests for folder hierarchy and entity structure
   - Tests drive endpoints with mock data

3. **test_template_recursion.py**
   - Tests for nested folder template structures
   - Validates recursive folder creation

### Advanced Tests

4. **test_real_drive_integration.py** 🔐
   - **Integration tests** that require real Google Drive credentials
   - Marked with `@pytest.mark.integration`
   - **Automatically skipped** if `GOOGLE_SERVICE_ACCOUNT_JSON` is not configured
   - Tests real Drive API operations (create folders, list files, etc.)
   - **Not run by default in CI/CD pipelines**

5. **test_concurrent_access.py** ⚡
   - Tests for concurrent access to endpoints
   - Validates thread-safety and race condition handling
   - Simulates multiple simultaneous requests
   - Tests database consistency under concurrent load

6. **test_database_constraints.py** 🗄️
   - Tests for database integrity constraints
   - Validates uniqueness constraints (folder_id, file_id, template name)
   - Tests foreign key relationships
   - Ensures proper SQLAlchemy exception handling

## Running Tests

### Run all tests (default)
```bash
USE_MOCK_DRIVE=true pytest tests/ -v
```

### Run tests excluding integration tests
```bash
USE_MOCK_DRIVE=true pytest tests/ -m "not integration" -v
```

### Run only integration tests (requires credentials)
```bash
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}' \
pytest tests/ -m "integration" -v
```

### Run specific test file
```bash
USE_MOCK_DRIVE=true pytest tests/test_concurrent_access.py -v
```

### Run a specific test
```bash
USE_MOCK_DRIVE=true pytest tests/test_database_constraints.py::TestDriveFolderConstraints::test_drive_folder_unique_folder_id -v
```

## Test Markers

The project uses pytest markers to categorize tests:

- **`integration`**: Tests that require external services (Google Drive API)
- **`unit`**: Pure unit tests with no external dependencies

Configure markers in `pytest.ini`.

## Environment Variables

- **`USE_MOCK_DRIVE`**: Set to `"true"` to use mock Drive service (default for testing)
- **`GOOGLE_SERVICE_ACCOUNT_JSON`**: Google service account credentials (required for integration tests)
- **`DRIVE_ROOT_FOLDER_ID`**: Optional root folder ID for isolating test files in Drive

## CI/CD Considerations

For continuous integration pipelines:

1. **Default test run**: Uses mock Drive service, skips integration tests
   ```bash
   USE_MOCK_DRIVE=true pytest tests/ -m "not integration"
   ```

2. **Optional integration tests**: Can be run separately with credentials
   ```bash
   pytest tests/ -m "integration"
   ```

## Test Database Files

Tests create temporary SQLite databases:
- `test.db` - Used by test_hierarchy.py
- `test_concurrent.db` - Used by test_concurrent_access.py
- `test_template.db` - Used by test_template_recursion.py
- `test_constraints.db` - Used by test_database_constraints.py

These are automatically cleaned up after test runs.

## Test Coverage

Current test coverage includes:
- ✅ Mock Drive service functionality
- ✅ Folder hierarchy creation
- ✅ Template-based folder structures
- ✅ Concurrent request handling
- ✅ Database constraint validation
- ✅ Real Drive API integration (optional)

## Adding New Tests

When adding new tests:

1. Follow existing test patterns
2. Use appropriate fixtures for database setup
3. Mark integration tests with `@pytest.mark.integration`
4. Ensure tests clean up after themselves
5. Document any special requirements or environment variables
