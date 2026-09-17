import { Injectable, signal, inject } from '@angular/core';
import { ApiService } from './api.service';
import { InspectionService } from './inspection.service';
import { User } from '../models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private api = inject(ApiService);
  private inspection = inject(InspectionService);
  readonly user = signal<User | null | undefined>(undefined);
  async load() { try { this.user.set(await this.api.request<User>('/api/auth/me')); } catch { this.user.set(null); } }
  async login(username: string, password: string) { this.user.set(await this.api.request<User>('/api/auth/login', { method: 'POST', body: { username, password } })); }
  async logout() { await this.api.request<void>('/api/auth/logout', { method: 'POST', inspection: false }); this.inspection.toggle(false); this.user.set(null); }
  async changePassword(current_password: string, new_password: string) { await this.api.request('/api/auth/password', { method: 'POST', body: { current_password, new_password } }); this.user.set(null); }
}
