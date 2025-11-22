# Agent B TODO Enforcement Plan

## Opportunity to Improve

### Current Problem
Agent B frequently deviates from Agent A's carefully crafted execution plans, adding unsolicited operations that waste the limited 15-loop budget and make debugging difficult. This overstepping behavior was observed in multiple debug cycles (b7794e86, 21027932, 18efcb6a) where Agent B performed extra file operations beyond the original intent.

### Benefits of TODO Enforcement
- **Improved Plan Adherence**: Agent B will stick to approved steps, reducing wasted iterations
- **Better Resource Utilization**: With only 15 loops available, each must count toward the goal
- **Enhanced Debuggability**: Clearer execution traces when agents follow structured plans
- **Predictable Behavior**: Users get more consistent, focused execution
- **Reduced LLM Costs**: Fewer unnecessary tool calls and retries

### Strategic Alignment
This aligns with our "Go Upstream" principle - solving the root cause of overstepping rather than adding downstream constraints. It also supports our error recovery limits by ensuring Agent B uses its constrained loops efficiently.

## Issue Analysis

### Root Cause
Agent B operates in a ReAct loop with full tool access and broad "Senior DevOps Engineer" persona, but lacks explicit boundaries on what operations are approved. The current prompt gives Agent B autonomy to "adapt to errors or unexpected results" which can lead to scope creep.

### Observed Behaviors
From debug cycles:
- **Extra File Operations**: Agent B adds `read_file` calls after `run_command ls`
- **Unplanned Explorations**: Agent B investigates files/directories not mentioned in the original plan
- **Scope Expansion**: Single-step plans balloon into multi-step investigations
- **Resource Waste**: Limited 15-loop budget gets consumed on tangential activities

### Impact Assessment
- **Performance**: Up to 45 LLM calls wasted (15 loops × 3 retries) on non-essential work
- **Reliability**: Unpredictable execution makes it harder to trust automation
- **Debugging**: Mixed signals between planned vs unplanned operations
- **User Experience**: Slower responses and unexpected side effects

## Implementation Plan

### Phase 1: Design TODO Structure

#### Task 1.1: Define TODO Schema
- **Objective**: Create a structured format for Agent A to specify approved operations
- **Requirements**:
  - JSON-compatible structure for tool call serialization
  - Hierarchical organization (main tasks with subtasks)
  - Clear success criteria per task
  - Optional vs required operations
- **Deliverable**: TODO format specification in prompts.py

#### Task 1.2: Update Agent A Prompt
- **Objective**: Train Agent A to generate TODO lists instead of free-form plans
- **Requirements**:
  - Include TODO generation in system prompt
  - Provide examples of good TODO structures
  - Balance flexibility with structure
- **Deliverable**: Updated AGENT_A_SYSTEM_PROMPT

### Phase 2: Agent B Enforcement

#### Task 2.1: Modify Agent B Prompt
- **Objective**: Add TODO enforcement rules to Agent B's system prompt
- **Requirements**:
  - Require TODO validation before each tool call
  - Allow only approved operations
  - Permit TODO modifications only under specific conditions
  - Maintain error recovery capabilities
- **Deliverable**: Updated AGENT_B_SYSTEM_PROMPT

#### Task 2.2: Add TODO Tracking Logic
- **Objective**: Implement runtime TODO state management
- **Requirements**:
  - Parse TODOs from Agent A's response
  - Track completion status
  - Validate tool calls against TODOs
  - Handle TODO modifications
- **Deliverable**: TODO validation functions in orchestrator.py

### Phase 3: Error Handling Integration

#### Task 3.1: Update Error Recovery
- **Objective**: Ensure TODO enforcement doesn't break error handling
- **Requirements**:
  - Allow emergency operations for error recovery
  - Maintain fallback to Agent A for complex issues
  - Log TODO violations for debugging
- **Deliverable**: Updated error handling in orchestrator.py

#### Task 3.2: Add TODO Modification Rules
- **Objective**: Define when and how Agent B can modify TODOs
- **Requirements**:
  - Clear criteria for TODO expansion
  - Approval workflow for major changes
  - Audit trail of modifications
- **Deliverable**: TODO modification policy in prompts

### Phase 4: Monitoring and Metrics

#### Task 4.1: Add TODO Metrics
- **Objective**: Track TODO adherence and effectiveness
- **Requirements**:
  - Completion rates per TODO item
  - Modification frequency
  - Loop utilization efficiency
  - Error rates with TODO enforcement
- **Deliverable**: TODO metrics in memory system

## Testing Strategy

### Unit Tests

#### Test 1.1: TODO Parsing
- **Objective**: Verify TODO structure parsing from Agent A responses
- **Test Cases**:
  - Valid TODO JSON structures
  - Malformed TODO handling
  - Empty TODO lists
  - Complex hierarchical TODOs

#### Test 1.2: TODO Validation
- **Objective**: Test tool call validation against TODOs
- **Test Cases**:
  - Approved tool calls pass validation
  - Unapproved tool calls are rejected
  - TODO completion tracking
  - Modification approval logic

### Integration Tests

#### Test 2.1: End-to-End Cycles
- **Objective**: Test complete cycles with TODO enforcement
- **Test Cases**:
  - Simple single-step plans
  - Complex multi-step workflows
  - Error recovery scenarios
  - TODO modification workflows

#### Test 2.2: Regression Prevention
- **Objective**: Ensure existing functionality still works
- **Test Cases**:
  - All existing test suites pass
  - Performance benchmarks maintained
  - Error handling unchanged for non-TODO scenarios

### Performance Tests

#### Test 3.1: Efficiency Metrics
- **Objective**: Measure improvement in resource utilization
- **Metrics**:
  - Average loops per successful cycle
  - LLM call reduction percentage
  - Response time improvements
  - Error rate changes

#### Test 3.2: Load Testing
- **Objective**: Ensure TODO enforcement scales
- **Test Cases**:
  - High-frequency request patterns
  - Complex multi-step plans
  - Concurrent execution scenarios

### User Acceptance Tests

#### Test 4.1: Real-World Scenarios
- **Objective**: Validate with actual user workflows
- **Test Cases**:
  - File system operations
  - Package management tasks
  - Development workflows
  - Debugging scenarios

#### Test 4.2: Edge Cases
- **Objective**: Test boundary conditions
- **Test Cases**:
  - Empty plans
  - Single-step plans
  - Maximum complexity plans
  - Error conditions

## Success Criteria

### Functional Success
- ✅ Agent B adheres to TODO lists in >95% of operations
- ✅ No regression in existing functionality
- ✅ Error recovery still works for genuine failures
- ✅ TODO modifications require proper justification

### Performance Success
- ✅ 20-30% reduction in average LLM calls per cycle
- ✅ Improved loop utilization (fewer wasted iterations)
- ✅ Response times maintained or improved
- ✅ No increase in error rates

### Quality Success
- ✅ All tests pass (unit, integration, performance)
- ✅ Code review approval
- ✅ Documentation updated
- ✅ Monitoring dashboards show positive trends

## Risk Assessment

### Technical Risks
- **Over-Constriction**: TODO enforcement might be too rigid, preventing legitimate adaptations
- **Parsing Failures**: TODO structure issues could break cycles
- **Performance Impact**: Additional validation might slow execution

### Mitigation Strategies
- **Gradual Rollout**: Start with optional enforcement, make mandatory after validation
- **Fallback Mechanisms**: Allow Agent A intervention for stuck cycles
- **Monitoring**: Extensive logging to detect and fix issues quickly

### Rollback Plan
- Feature flag to disable TODO enforcement
- Quick revert to previous Agent B prompt
- Database migration to handle TODO data cleanup

## Timeline

### Week 1: Design and Planning
- Complete TODO schema design
- Update Agent A prompt
- Create initial test cases

### Week 2: Core Implementation
- Implement TODO tracking logic
- Update Agent B prompt
- Add validation functions

### Week 3: Error Handling
- Integrate with error recovery
- Add TODO modification rules
- Implement monitoring

### Week 4: Testing and Validation
- Complete all test suites
- Performance benchmarking
- User acceptance testing

### Week 5: Deployment and Monitoring
- Gradual rollout with feature flags
- Production monitoring
- Issue resolution and refinements

## Dependencies

### External Dependencies
- None - all changes within existing codebase

### Internal Dependencies
- Agent A/B prompt system (orchestrator/prompts.py)
- Orchestrator execution logic (orchestrator/orchestrator.py)
- Memory system for metrics (memory/api.py)

## Future Enhancements

### Phase 2 Opportunities
- **Learning from History**: Use past successful TODO patterns to improve Agent A planning
- **Dynamic TODOs**: Allow runtime TODO expansion based on learned patterns
- **User Overrides**: Let users approve/reject TODO modifications
- **Multi-Agent TODOs**: Coordinate TODOs across multiple agents

### Long-term Vision
- **Autonomous Planning**: Agent B learns to create its own TODOs for complex tasks
- **Collaborative Planning**: Multiple agents co-create TODOs for complex workflows
- **Self-Optimization**: System learns optimal TODO granularity for different task types</content>
<parameter name="filePath">/home/ubuntu/apps/ai-terminal/history/agent_b_todo-enforcement.md