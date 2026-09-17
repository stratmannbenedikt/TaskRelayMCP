import { Injectable, signal } from '@angular/core';

export interface DashboardPreferences { showDescription: boolean; showTaskPreview: boolean; previewCount: 0 | 3 | 5 | 10; showLatestActivity: boolean; showRecentNote: boolean; showArchived: boolean; }
const defaults: DashboardPreferences = { showDescription: true, showTaskPreview: true, previewCount: 3, showLatestActivity: true, showRecentNote: true, showArchived: false };

@Injectable({ providedIn: 'root' })
export class DashboardPreferencesService {
  readonly value = signal<DashboardPreferences>(this.read());
  update(value: Partial<DashboardPreferences>) { const next = { ...this.value(), ...value }; this.value.set(next); localStorage.setItem('taskrelay.dashboard-preferences', JSON.stringify(next)); }
  private read(): DashboardPreferences { try { const value = JSON.parse(localStorage.getItem('taskrelay.dashboard-preferences') ?? '{}'); return { ...defaults, ...value, previewCount: [0, 3, 5, 10].includes(value.previewCount) ? value.previewCount : 3 }; } catch { return { ...defaults }; } }
}
