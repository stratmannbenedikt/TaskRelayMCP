import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { ProjectLandingComponent } from './project-landing.component';
import { ApiService } from '../core/api.service';
import { InspectionService } from '../core/inspection.service';

describe('ProjectLandingComponent', () => {
  it('opens Tasks first when both capabilities are enabled', async () => {
    const router = await create([{ key: 'both', tasks_enabled: true, notes_enabled: true }]);
    expect(router.navigateByUrl).toHaveBeenCalledWith('/projects/both/tasks', { replaceUrl: true });
  });
  it('opens Notes for a notes-only project', async () => {
    const router = await create([{ key: 'notes', tasks_enabled: false, notes_enabled: true }]);
    expect(router.navigateByUrl).toHaveBeenCalledWith('/projects/notes/notes', { replaceUrl: true });
  });
  it('returns to projects when the project is inaccessible', async () => {
    const router = await create([]);
    expect(router.navigateByUrl).toHaveBeenCalledWith('/home', { replaceUrl: true });
  });
});

async function create(projects: unknown[]) {
  await TestBed.configureTestingModule({ imports: [ProjectLandingComponent], providers: [provideRouter([]), { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => projects[0] ? (projects[0] as { key: string }).key : 'missing' } } } }, { provide: ApiService, useValue: { request: vi.fn().mockResolvedValue(projects) } }, { provide: InspectionService, useValue: { active: () => false } }] }).compileComponents();
  const router = TestBed.inject(Router); vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  const fixture = TestBed.createComponent(ProjectLandingComponent); fixture.detectChanges(); await fixture.whenStable(); return router;
}
