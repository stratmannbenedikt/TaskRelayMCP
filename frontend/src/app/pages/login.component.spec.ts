import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { LoginComponent } from './login.component';
import { AuthService } from '../core/auth.service';

describe('LoginComponent', () => {
  it('returns to the original internal route after login', async () => {
    const router = await create('/projects/notes/notes', false);
    expect(router.navigateByUrl).toHaveBeenCalledWith('/projects/notes/notes');
  });
  it('falls back from a malicious return URL', async () => {
    const router = await create('//evil.example', false);
    expect(router.navigateByUrl).toHaveBeenCalledWith('/home');
  });
  it('preserves the return URL through mandatory password change', async () => {
    const router = await create('/projects/notes/notes', true);
    expect(router.navigateByUrl).toHaveBeenCalledWith('/password-change?returnUrl=%2Fprojects%2Fnotes%2Fnotes');
  });
});

async function create(returnUrl: string, must_change_password: boolean) {
  const login = vi.fn().mockResolvedValue(undefined);
  await TestBed.configureTestingModule({ imports: [LoginComponent], providers: [{ provide: Router, useValue: { navigateByUrl: vi.fn().mockResolvedValue(true) } }, { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: { get: () => returnUrl } } } }, { provide: AuthService, useValue: { login, user: () => ({ must_change_password }) } }] }).compileComponents();
  const fixture = TestBed.createComponent(LoginComponent);
  fixture.componentInstance.form.setValue({ username: 'user', password: 'password' });
  await fixture.componentInstance.login();
  expect(login).toHaveBeenCalledWith('user', 'password');
  return TestBed.inject(Router);
}
