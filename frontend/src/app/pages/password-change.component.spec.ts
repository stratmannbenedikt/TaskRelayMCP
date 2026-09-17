import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { PasswordChangeComponent } from './password-change.component';
import { AuthService } from '../core/auth.service';

describe('PasswordChangeComponent', () => {
  it('preserves the return URL for the required second login', async () => {
    const changePassword = vi.fn().mockResolvedValue(undefined), navigateByUrl = vi.fn().mockResolvedValue(true);
    await TestBed.configureTestingModule({ imports: [PasswordChangeComponent], providers: [{ provide: Router, useValue: { navigateByUrl } }, { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: { get: () => '/projects/notes/notes' } } } }, { provide: AuthService, useValue: { changePassword } }] }).compileComponents();
    const fixture = TestBed.createComponent(PasswordChangeComponent);
    fixture.componentInstance.form.setValue({ current: 'temporary', password: 'long-enough-password' });
    await fixture.componentInstance.change();
    expect(changePassword).toHaveBeenCalledWith('temporary', 'long-enough-password');
    expect(navigateByUrl).toHaveBeenCalledWith('/login?returnUrl=%2Fprojects%2Fnotes%2Fnotes');
  });
});
