import { TaskFilterBarComponent } from './task-filter-bar.component';
import { TestBed } from '@angular/core/testing';

describe('TaskFilterBarComponent', () => {
  it('keeps project optional and emits repeated tag IDs', () => {
    const component = new TaskFilterBarComponent(); component.showProject = false; component.state = { q: '', project: 'one', status: 'TODO', priority: '', assignment: 'all', tagIds: [1, 2], sort: 'priority' }; component.ngOnChanges();
    expect(component.value()).toMatchObject({ project: 'one', tagIds: [1, 2] });
  });
  it('closes filters on mobile transitions and removes its media listener', () => {
    const listeners = new Set<(event: MediaQueryListEvent) => void>(), media = { matches: true, addEventListener: vi.fn((_: string, listener: (event: MediaQueryListEvent) => void) => listeners.add(listener)), removeEventListener: vi.fn((_: string, listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener)) };
    vi.stubGlobal('matchMedia', vi.fn(() => media));
    const fixture = TestBed.createComponent(TaskFilterBarComponent), component = fixture.componentInstance;
    component.state = { q: 'urgent', project: '', status: 'TODO', priority: 'HIGH', assignment: 'all', tagIds: [], sort: 'priority' }; component.ngOnChanges(); fixture.detectChanges();
    expect(component.desktop()).toBe(true);
    media.matches = false; listeners.forEach(listener => listener({ matches: false } as MediaQueryListEvent)); fixture.detectChanges();
    const body = fixture.nativeElement.querySelector('#task-filter-body') as HTMLElement, toggle = fixture.nativeElement.querySelector('.filter-toggle') as HTMLButtonElement;
    expect(body.hidden).toBe(true); expect(body.getAttribute('inert')).toBe(''); expect(toggle.textContent).toContain('Filters (2)');
    toggle.click(); fixture.detectChanges(); expect(body.hidden).toBe(false); expect(toggle.getAttribute('aria-expanded')).toBe('true');
    fixture.destroy(); expect(media.removeEventListener).toHaveBeenCalledOnce(); vi.unstubAllGlobals();
  });
  it('provides stable grid hooks for the global filter band', () => {
    const fixture = TestBed.createComponent(TaskFilterBarComponent); fixture.componentInstance.showProject = true; fixture.detectChanges();
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelector('form')?.classList).toContain('with-project');
    expect(['filter-text', 'filter-project', 'filter-status', 'filter-priority', 'filter-assignment', 'filter-tags', 'filter-sort', 'filter-actions'].every(selector => page.querySelector(`.${selector}`))).toBe(true);
  });
});
