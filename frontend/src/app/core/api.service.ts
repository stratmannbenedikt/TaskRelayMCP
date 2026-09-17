import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { catchError, firstValueFrom, throwError } from 'rxjs';
import { InspectionService } from './inspection.service';

export class ApiError extends Error { constructor(message: string, readonly status: number) { super(message); } }

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private inspection = inject(InspectionService);

  request<T>(path: string, options: { method?: string; body?: unknown; inspection?: boolean } = {}): Promise<T> {
    const headers = new HttpHeaders({ 'Content-Type': 'application/json', ...(options.inspection === false ? {} : { 'X-TaskRelay-Inspection': String(this.inspection.active()) }) });
    return firstValueFrom(this.http.request<T>(options.method ?? 'GET', path, { body: options.body, headers, withCredentials: true }).pipe(
      catchError(error => throwError(() => new ApiError(this.errorMessage(error), error.status ?? 0))),
    ));
  }

  private errorMessage(error: HttpErrorResponse): string {
    const detail = error.error?.detail;
    return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : error.message || 'Request failed';
  }
}
