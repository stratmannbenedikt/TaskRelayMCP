import { TagProposal } from '../models';
import { TagManagementComponent } from './tag-management.component';

describe('TagManagementComponent', () => {
  it('loads the exact pending proposal response into an approval with retroactive assignment enabled', () => {
    const reset = vi.fn(), reviewing = { set: vi.fn() };
    const component = { reviewing, proposalForm: { reset } } as unknown as TagManagementComponent;
    TagManagementComponent.prototype.review.call(component, proposal());
    expect(reviewing.set).toHaveBeenCalledWith(proposal());
    expect(reset).toHaveBeenCalledWith({ name: 'needs-review', color: '#336699', description: 'Agent request', apply_requested_tasks: true });
  });
  it('blocks invalid proposal names and submits a normalized valid payload', async () => {
    const request = vi.fn(), reviewing = Object.assign(() => proposal(), { set: vi.fn() });
    const invalid = { getRawValue: () => ({ name: 'bad--slug', color: '#336699', description: ' x ', apply_requested_tasks: true }), patchValue: vi.fn(), invalid: true, markAllAsTouched: vi.fn() };
    await TagManagementComponent.prototype.approve.call({ reviewing, proposalForm: invalid });
    expect(invalid.markAllAsTouched).toHaveBeenCalled();
    const valid = { getRawValue: () => ({ name: ' Needs-Review ', color: '#336699', description: ' Agent request ', apply_requested_tasks: true }), patchValue: vi.fn(), invalid: false, markAllAsTouched: vi.fn() };
    const component = { reviewing, proposalForm: valid, run: async (action: () => Promise<unknown>) => action(), api: { request } } as unknown as TagManagementComponent;
    await TagManagementComponent.prototype.approve.call(component);
    expect(request).toHaveBeenCalledWith('/api/tag-proposals/9/approve', { method: 'POST', body: { name: 'needs-review', color: '#336699', description: 'Agent request', apply_requested_tasks: true } });
  });
  it('allows tag writes only for active member projects and owner-only tag administration', () => {
    expect(TagManagementComponent.prototype.writable.call({ project: () => ({ role: 'MEMBER', archived: false }), inspection: { active: () => false } })).toBe(true);
    expect(TagManagementComponent.prototype.owner.call({ project: () => ({ role: 'MEMBER' }) })).toBe(false);
    expect(TagManagementComponent.prototype.owner.call({ project: () => ({ role: 'OWNER' }) })).toBe(true);
    expect(TagManagementComponent.prototype.writable.call({ project: () => ({ role: 'OWNER', archived: true }), inspection: { active: () => false } })).toBe(false);
    expect(TagManagementComponent.prototype.writable.call({ project: () => ({ role: 'OWNER', archived: false }), inspection: { active: () => true } })).toBe(false);
  });
});

function proposal(): TagProposal { return { id: 9, project: 'alpha', name: 'needs-review', color: '#336699', description: 'Agent request', status: 'PENDING', proposed_by: 'agent-user', mcp_key: 'agent-key', created_at: '2026-01-01T00:00:00Z', expires_at: '2026-01-08T00:00:00Z', decided_by: null, decided_at: null, resolved_tag_id: null, task_ids: [4, 5] }; }
