import { DashboardPreferencesService } from './dashboard-preferences.service';

describe('DashboardPreferencesService', () => {
  beforeEach(() => localStorage.clear());
  it('uses safe defaults for missing or corrupt storage', () => {
    expect(new DashboardPreferencesService().value().previewCount).toBe(3);
    localStorage.setItem('taskrelay.dashboard-preferences', '{bad');
    expect(new DashboardPreferencesService().value().showDescription).toBe(true);
  });
});
