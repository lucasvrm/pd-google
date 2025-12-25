# Golden Rules V2 - Complete Integration Guide

**Version:** 2.0  
**Last Updated:** 2025-12-25  
**Repository:** pipedesk-koa

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Architecture & Design](#architecture--design)
3. [Code Quality & Standards](#code-quality--standards)
4. [Testing & Validation](#testing--validation)
5. [Security & Performance](#security--performance)
6. [Documentation & Communication](#documentation--communication)
7. [New Rules (14-21)](#new-rules-14-21)

---

## Core Principles

### Rule 1: Single Responsibility Principle
- Each module, class, or function should have one and only one reason to change
- Keep functions focused and concise (ideally under 20 lines)
- Extract complex logic into separate, well-named functions
- Avoid god objects or functions that do too much

### Rule 2: DRY (Don't Repeat Yourself)
- Abstract common patterns into reusable utilities
- Use composition over duplication
- Create shared modules for repeated functionality
- Maintain a single source of truth for business logic

### Rule 3: KISS (Keep It Simple, Stupid)
- Favor simplicity over cleverness
- Write code that others can easily understand
- Avoid premature optimization
- Use straightforward solutions unless complexity is justified

---

## Architecture & Design

### Rule 4: Separation of Concerns
- Clearly separate presentation, business logic, and data access layers
- Use middleware for cross-cutting concerns (logging, auth, validation)
- Keep routes thin - delegate to services
- Maintain clear boundaries between modules

**Example Structure:**
```
routes/ → Controllers → Services → Repositories → Models
```

### Rule 5: Dependency Injection
- Pass dependencies explicitly rather than importing them directly
- Makes code more testable and maintainable
- Use constructor injection for required dependencies
- Consider using a DI container for complex applications

### Rule 6: API Design Excellence
- Use RESTful conventions consistently
- Version your APIs (e.g., /api/v1/)
- Return appropriate HTTP status codes
- Provide clear, structured error messages
- Document all endpoints with examples

**HTTP Status Code Guide:**
- 200: Success
- 201: Created
- 204: No Content
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 500: Internal Server Error

---

## Code Quality & Standards

### Rule 7: Error Handling
- Always handle errors explicitly
- Use try-catch blocks appropriately
- Never swallow errors silently
- Log errors with context (request ID, user ID, timestamp)
- Return user-friendly error messages
- Use custom error classes for different error types

**Example:**
```javascript
class ValidationError extends Error {
  constructor(message, field) {
    super(message);
    this.name = 'ValidationError';
    this.field = field;
    this.statusCode = 400;
  }
}
```

### Rule 8: Code Style & Formatting
- Follow ESLint configuration strictly
- Use Prettier for consistent formatting
- Naming conventions:
  - camelCase for variables and functions
  - PascalCase for classes
  - UPPER_SNAKE_CASE for constants
  - Descriptive names over abbreviations
- Keep line length under 100 characters
- Use meaningful variable names (no single letters except in loops)

### Rule 9: Type Safety
- Use JSDoc comments for type hints in JavaScript
- Consider TypeScript for large projects
- Validate input types at API boundaries
- Use schema validation (e.g., Joi, Yup)

### Rule 10: Async/Await Best Practices
- Always use async/await over raw promises
- Handle promise rejections
- Avoid blocking the event loop
- Use Promise.all() for parallel operations
- Don't forget to await async functions

---

## Testing & Validation

### Rule 11: Test Coverage
- Maintain minimum 80% code coverage
- Write unit tests for business logic
- Write integration tests for API endpoints
- Use test-driven development (TDD) when appropriate
- Mock external dependencies

**Test Structure:**
```javascript
describe('Feature', () => {
  describe('Scenario', () => {
    it('should behave as expected', async () => {
      // Arrange
      // Act
      // Assert
    });
  });
});
```

### Rule 12: Input Validation
- Validate all user inputs
- Sanitize data to prevent injection attacks
- Use middleware for validation
- Provide clear validation error messages
- Never trust client-side validation alone

---

## Security & Performance

### Rule 13: Security First
- Never commit secrets or credentials
- Use environment variables for configuration
- Implement proper authentication and authorization
- Use HTTPS in production
- Sanitize user inputs to prevent XSS and SQL injection
- Keep dependencies updated
- Use security headers (helmet.js)
- Implement rate limiting
- Log security events

**Security Checklist:**
- [ ] Authentication implemented
- [ ] Authorization checks on all protected routes
- [ ] Input validation and sanitization
- [ ] CORS configured properly
- [ ] Rate limiting enabled
- [ ] Security headers set
- [ ] Dependencies audited regularly

---

## Documentation & Communication

### Rule 14: Documentation is Code
- Document the "why" not just the "what"
- Keep README files updated
- Use JSDoc for functions and classes
- Maintain API documentation (Swagger/OpenAPI)
- Document architectural decisions (ADRs)
- Include setup and deployment instructions

### Rule 15: Git Best Practices
- Write clear, descriptive commit messages
- Use conventional commits format
- Keep commits atomic and focused
- Never commit commented-out code
- Use feature branches
- Review code before merging

**Commit Message Format:**
```
type(scope): subject

body

footer
```

Types: feat, fix, docs, style, refactor, test, chore

---

## New Rules (14-21)

### Rule 16: Database Best Practices
- Use database transactions for multi-step operations
- Always use parameterized queries to prevent SQL injection
- Index frequently queried columns
- Optimize N+1 queries with eager loading
- Use database migrations for schema changes
- Back up data regularly
- Monitor slow queries and optimize

**Example Transaction:**
```javascript
const transaction = await sequelize.transaction();
try {
  await Model1.create(data1, { transaction });
  await Model2.update(data2, { transaction });
  await transaction.commit();
} catch (error) {
  await transaction.rollback();
  throw error;
}
```

### Rule 17: Performance Optimization
- Cache frequently accessed data
- Use pagination for large datasets
- Implement lazy loading where appropriate
- Compress responses (gzip)
- Optimize images and assets
- Use CDN for static content
- Monitor and profile performance regularly
- Set appropriate timeout values

**Caching Strategy:**
- Cache-Control headers for static assets
- Redis/Memcached for session data
- Application-level caching for expensive operations

### Rule 18: Logging & Monitoring
- Log all significant events
- Use structured logging (JSON format)
- Include request IDs for tracing
- Log levels: ERROR, WARN, INFO, DEBUG
- Never log sensitive information (passwords, tokens)
- Use centralized logging (e.g., ELK stack)
- Set up alerts for critical errors
- Monitor application metrics (response time, error rate)

**Log Example:**
```javascript
logger.info({
  requestId: req.id,
  userId: req.user.id,
  action: 'user.login',
  timestamp: new Date().toISOString(),
  metadata: { ip: req.ip }
});
```

### Rule 19: Configuration Management
- Use environment-specific configuration files
- Never hardcode configuration values
- Validate configuration on startup
- Use .env files for local development
- Use secure secret management in production (Vault, AWS Secrets Manager)
- Document all configuration options
- Provide sensible defaults

**Configuration Structure:**
```javascript
config/
  ├── default.js
  ├── development.js
  ├── production.js
  └── test.js
```

### Rule 20: Code Review Standards
- All code must be reviewed before merging
- Review for logic, readability, and security
- Provide constructive feedback
- Test the changes locally when possible
- Check for test coverage
- Ensure documentation is updated
- Verify no secrets are committed

**Review Checklist:**
- [ ] Code follows style guidelines
- [ ] Tests are included and passing
- [ ] Documentation is updated
- [ ] No security vulnerabilities
- [ ] Performance considerations addressed
- [ ] Error handling is proper
- [ ] Commit messages are clear

### Rule 21: Continuous Integration/Deployment
- Automate testing in CI pipeline
- Run linting and formatting checks
- Perform security scans
- Auto-deploy to staging on merge to develop
- Require manual approval for production
- Use blue-green or canary deployments
- Implement rollback strategy
- Monitor deployments

**CI/CD Pipeline Stages:**
1. Lint & Format Check
2. Run Unit Tests
3. Run Integration Tests
4. Security Scan
5. Build Application
6. Deploy to Environment
7. Run Smoke Tests
8. Monitor & Alert

---

## Quick Reference

### Before Committing Checklist
- [ ] Code follows all golden rules
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] No console.logs or debugging code
- [ ] No secrets or credentials
- [ ] Code reviewed by peer
- [ ] Linting passes
- [ ] Git commit message is clear

### Code Smell Indicators
- Functions longer than 50 lines
- Files longer than 500 lines
- Deeply nested conditionals (>3 levels)
- Duplicated code blocks
- Cryptic variable names
- Magic numbers without constants
- Commented-out code
- Lack of error handling

### Refactoring Triggers
- When you need to change code in multiple places for one feature
- When understanding code requires extensive comments
- When adding a feature takes significantly longer than expected
- When tests are hard to write
- When code coverage drops below 80%

---

## Implementation Guidelines

### Priority Levels

**P0 (Critical):** Must be followed always
- Security practices (Rule 13)
- Error handling (Rule 7)
- Input validation (Rule 12)
- Git best practices (Rule 15)

**P1 (High):** Should be followed in most cases
- Testing coverage (Rule 11)
- Code style (Rule 8)
- Documentation (Rule 14)
- Performance optimization (Rule 17)

**P2 (Medium):** Follow when practical
- Type safety (Rule 9)
- Dependency injection (Rule 5)
- Refactoring triggers

---

## Exceptions

Rules can be broken when:
1. There's a clear, documented reason
2. The team agrees on the exception
3. The exception is noted in code comments
4. The exception is temporary with a plan to address

**Exception Format:**
```javascript
// EXCEPTION: [Rule Number] - [Reason]
// TODO: [Plan to address] - [Date]
```

---

## Version History

- **v2.0** (2025-12-25): Added Rules 14-21 with comprehensive coverage of documentation, database, performance, logging, configuration, code review, and CI/CD
- **v1.0**: Initial golden rules (Rules 1-13)

---

## Contributing

These rules are living documents. If you have suggestions:
1. Create an issue describing the proposed rule/change
2. Discuss with the team
3. Update this document with team consensus
4. Increment version number

---

## Resources

- [Clean Code by Robert C. Martin](https://www.amazon.com/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350882)
- [Node.js Best Practices](https://github.com/goldbergyoni/nodebestpractices)
- [Koa.js Documentation](https://koajs.com/)
- [JavaScript Style Guide](https://github.com/airbnb/javascript)
- [OWASP Security Practices](https://owasp.org/)

---

**Remember:** These rules exist to help us write better, more maintainable code. They're guidelines, not handcuffs. Use good judgment, and when in doubt, discuss with the team.

**Happy Coding! 🚀**
