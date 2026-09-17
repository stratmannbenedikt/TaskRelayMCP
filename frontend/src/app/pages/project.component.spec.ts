import { ProjectComponent } from './project.component';

describe('ProjectComponent task drawer', () => {
  it('is not writable when archived', () => {
    const component = { project: () => ({ role: 'OWNER', archived: true }), inspection: { active: () => false } } as unknown as ProjectComponent;
    expect(ProjectComponent.prototype.writable.call(component)).toBe(false);
  });
  it('starts selected tasks in read mode and only edits explicitly', () => {
    const component = { selected: { set: vi.fn() }, mode: { set: vi.fn() }, editTask: { reset: vi.fn(), getRawValue: () => ({}), markAsPristine: vi.fn() }, members: () => [], completeForm: { reset: vi.fn() } } as unknown as ProjectComponent;
    ProjectComponent.prototype.select.call(component, { id: 7, title: 'Read first', description: '', priority: 'NORMAL', target_project: 'one', tags: [], assignee: null } as never);
    expect(component['mode'].set).toHaveBeenCalledWith('read');
    ProjectComponent.prototype.edit.call(component);
    expect(component['mode'].set).toHaveBeenLastCalledWith('edit');
  });
  it('requires confirmation before discarding a dirty edit', () => {
    const component = { discard: () => false, selected: { set: vi.fn() }, key: () => 'one', router: { navigateByUrl: vi.fn() } } as unknown as ProjectComponent;
    vi.stubGlobal('confirm', vi.fn(() => false));
    ProjectComponent.prototype.close.call(component);
    expect(component['selected'].set).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
  it('uses one discard decision for route changes and before unload', () => {
    const component = { hasUnsavedChanges: () => true } as unknown as ProjectComponent;
    vi.stubGlobal('confirm', vi.fn(() => false));
    expect(ProjectComponent.prototype.canDeactivate.call(component)).toBe(false);
    const event = { preventDefault: vi.fn(), returnValue: undefined } as unknown as BeforeUnloadEvent;
    ProjectComponent.prototype.beforeUnload.call(component, event);
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(confirm).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
  it('restores the rendered New task trigger from a local intent', () => {
    document.body.innerHTML = '<header class="page-title"><button>New task</button></header>';
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => callback(0));
    const component = { restoreIntent: 'new', loadGeneration: 0, host: { nativeElement: document.body }, focusAfterRender: ProjectComponent.prototype['focusAfterRender'] } as unknown as ProjectComponent;
    ProjectComponent.prototype['focusAfterRender'].call(component);
    expect(document.querySelector('button')).toBe(document.activeElement);
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });
  it('ignores a stale task detail after navigating back to the task list', async () => {
    let taskId: string | null = '7';
    let resolveTask!: (task: unknown) => void;
    const component = {
      loadGeneration: 0, key: () => 'one', inspection: { active: () => false }, route: { snapshot: { paramMap: { get: (name: string) => name === 'taskId' ? taskId : 'one' } }, },
      api: { request: (path: string) => {
        if (path.startsWith('/api/projects?')) return Promise.resolve([{ key: 'one', tasks_enabled: true, role: 'OWNER' }]);
        if (path.startsWith('/api/tasks/7?')) return new Promise(resolve => { resolveTask = resolve; });
        if (path.startsWith('/api/tasks?')) return Promise.resolve([]);
        if (path.startsWith('/api/projects/one/tags')) return Promise.resolve([]);
        if (path === '/api/directory') return Promise.resolve([]);
        return Promise.resolve([]);
      } },
      restoreIntent: 'task-7', error: { set: vi.fn() }, selected: { set: vi.fn() }, projects: { set: vi.fn() }, project: { set: vi.fn() }, tasks: { set: vi.fn() }, tags: { set: vi.fn() }, directory: { set: vi.fn() }, members: { set: vi.fn() }, select: vi.fn(), focusAfterRender: vi.fn(), router: { navigateByUrl: vi.fn() },
      loadTask: ProjectComponent.prototype['loadTask'],
    } as unknown as ProjectComponent;
    const detailLoad = ProjectComponent.prototype.load.call(component);
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    taskId = null;
    await ProjectComponent.prototype.load.call(component);
    resolveTask({ id: 7, target_project: 'one' });
    await detailLoad;
    expect(component['select']).not.toHaveBeenCalled();
    expect(component['focusAfterRender']).toHaveBeenCalledOnce();
  });
});
