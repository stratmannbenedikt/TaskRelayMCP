import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ApiService } from './api.service';
import { InspectionService } from './inspection.service';
import { AuthService } from './auth.service';

describe('ApiService', () => {
  let api: ApiService; let inspection: InspectionService; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }); api = TestBed.inject(ApiService); inspection = TestBed.inject(InspectionService); http = TestBed.inject(HttpTestingController); });
  afterEach(() => http.verify());

  it('sends the inspection marker on normal requests and bypasses it for logout', async () => {
    inspection.toggle(true);
    const projectRequest = api.request('/api/projects');
    const request = http.expectOne('/api/projects');
    expect(request.request.headers.get('X-TaskRelay-Inspection')).toBe('true');
    request.flush([]);
    await projectRequest;

    const logout = TestBed.inject(AuthService).logout();
    const logoutRequest = http.expectOne('/api/auth/logout');
    expect(logoutRequest.request.headers.has('X-TaskRelay-Inspection')).toBe(false);
    logoutRequest.flush(null);
    await logout;

    const login = TestBed.inject(AuthService).login('user', 'password');
    const loginRequest = http.expectOne('/api/auth/login');
    expect(loginRequest.request.headers.get('X-TaskRelay-Inspection')).toBe('false');
    loginRequest.flush({ id: 1, username: 'user', display_name: 'User', active: true, is_admin: false, must_change_password: false });
    await login;
  });

  it('uses the API error detail', async () => {
    const request = api.request('/api/projects');
    http.expectOne('/api/projects').flush({ detail: 'Project key already exists' }, { status: 409, statusText: 'Conflict' });
    await expect(request).rejects.toThrow('Project key already exists');
  });
});
