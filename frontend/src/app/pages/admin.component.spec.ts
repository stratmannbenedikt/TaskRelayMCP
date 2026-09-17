import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AdminComponent } from './admin.component';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { InspectionService } from '../core/inspection.service';

describe('AdminComponent', () => {
  it('shows validation feedback without posting invalid users', async () => {
    const request = vi.fn().mockResolvedValue([]);
    const fixture = await createComponent(request);
    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    expect(request).not.toHaveBeenCalledWith('/api/users', expect.anything());
    expect(fixture.nativeElement.textContent).toContain('Please correct the highlighted fields');
    expect(fixture.nativeElement.textContent).toContain('Enter a valid username.');
  });
  it('normalizes, submits, resets, and refreshes a user', async () => {
    const request = vi.fn().mockImplementation((path: string, options?: { method?: string }) => options?.method === 'POST' ? Promise.resolve({}) : Promise.resolve([]));
    const fixture = await createComponent(request);
    fixture.componentInstance.form.setValue({ username: ' User.Name ', display_name: 'User Name', temporary_password: 'long-enough-password', is_admin: false });
    await fixture.componentInstance.create();
    expect(request).toHaveBeenCalledWith('/api/users', expect.objectContaining({ body: expect.objectContaining({ username: 'user.name' }) }));
    expect(fixture.componentInstance.form.getRawValue()).toEqual({ username: '', display_name: '', temporary_password: '', is_admin: false });
    expect(request).toHaveBeenLastCalledWith('/api/users');
  });
});

async function createComponent(request: ReturnType<typeof vi.fn>) {
  await TestBed.configureTestingModule({ imports: [AdminComponent], providers: [provideRouter([]), { provide: ApiService, useValue: { request } }, { provide: AuthService, useValue: { user: () => undefined } }, { provide: InspectionService, useValue: { active: () => false } }] }).compileComponents();
  const fixture = TestBed.createComponent(AdminComponent); fixture.detectChanges(); await fixture.whenStable(); return fixture;
}
