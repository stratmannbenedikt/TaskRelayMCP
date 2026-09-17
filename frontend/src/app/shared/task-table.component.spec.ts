import { TaskTableComponent } from './task-table.component';
import { TestBed } from '@angular/core/testing';

describe('TaskTableComponent', () => {
  it('uses a deterministic description expansion threshold without opening the task', () => {
    const component = new TaskTableComponent(); expect(component.long('short')).toBe(false); expect(component.long('x'.repeat(121))).toBe(true); expect(component.descriptionId(7)).toBe('task-description-7'); component.toggle(7); expect(component.expanded()).toBe(7);
  });
  it('updates description expansion after a More click', () => {
    const fixture = TestBed.createComponent(TaskTableComponent), component = fixture.componentInstance;
    component.tasks = [{ id: 1, description: 'x'.repeat(121), updated_at: '2026-01-01' } as never, { id: 2, description: 'y'.repeat(121), updated_at: '2026-01-01' } as never]; fixture.detectChanges();
    const more = fixture.nativeElement.querySelector('.more') as HTMLButtonElement;
    more.click(); fixture.detectChanges();
    expect(more.getAttribute('aria-expanded')).toBe('true'); expect(fixture.nativeElement.querySelector('#task-description-1')?.getAttribute('aria-expanded')).toBe('true'); expect(fixture.nativeElement.querySelectorAll('.expanded')).toHaveLength(1);
  });
  it('keeps priority as data and emits tag/open actions separately', () => { const component = new TaskTableComponent(); const open = vi.fn(), tag = vi.fn(); component.open.subscribe(open); component.tagClick.subscribe(tag); component.open.emit({ id: 1 } as never); component.tagClick.emit(2); expect(open).toHaveBeenCalled(); expect(tag).toHaveBeenCalledWith(2); });
  it('renders one labeled priority rail with decorative vertical content', () => {
    const fixture = TestBed.createComponent(TaskTableComponent); fixture.componentInstance.tasks = [{ id: 1, description: '', priority: 'NORMAL', updated_at: '2026-01-01' } as never]; fixture.detectChanges();
    const row = fixture.nativeElement.querySelector('.task-row') as HTMLElement, rail = row.querySelector('.priority-rail') as HTMLElement;
    expect(row.dataset['priority']).toBe('NORMAL'); expect(row.querySelectorAll('.priority-rail')).toHaveLength(1); expect(rail.getAttribute('aria-label')).toBe('Priority: NORMAL'); expect(rail.querySelector('.priority-bar')?.getAttribute('aria-hidden')).toBe('true'); expect(rail.querySelector('.priority-label-vertical')?.getAttribute('aria-hidden')).toBe('true');
  });
  it('renders stable desktop areas with one title open affordance and relative time', () => {
    const fixture = TestBed.createComponent(TaskTableComponent), component = fixture.componentInstance, open = vi.fn();
    component.showProject = true; component.projects = [{ key: 'one', name: 'One' } as never]; component.tasks = [{ id: 1, title: 'Task', description: 'Description', priority: 'HIGH', status: 'TODO', target_project: 'one', assignee: null, tags: [], updated_at: '2026-01-01T00:00:00Z' } as never]; component.open.subscribe(open); fixture.detectChanges();
    const page = fixture.nativeElement as HTMLElement;
    expect(Array.from(page.querySelectorAll('.task-table-header span')).map(item => item.textContent?.trim())).toEqual(['Priority', 'Task', 'Project', 'Assignee', 'Tags', 'Updated']);
    expect(page.querySelectorAll('button')).toHaveLength(1); (page.querySelector('.task-title') as HTMLButtonElement).click(); expect(open).toHaveBeenCalledOnce();
    expect(page.querySelector('time.task-updated')?.getAttribute('datetime')).toBe('2026-01-01T00:00:00Z'); expect(page.querySelector('.task-main')).not.toBeNull(); expect(page.querySelector('.task-project')).not.toBeNull(); expect(page.querySelector('.task-tags')).not.toBeNull();
  });
});
