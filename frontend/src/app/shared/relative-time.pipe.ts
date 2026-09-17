import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'relativeTime' })
export class RelativeTimePipe implements PipeTransform {
  transform(value: string | Date, now = new Date()): string {
    const seconds = Math.trunc((new Date(value).getTime() - now.getTime()) / 1000);
    const [amount, unit]: [number, Intl.RelativeTimeFormatUnit] = Math.abs(seconds) < 60 ? [seconds, 'second'] : Math.abs(seconds) < 3600 ? [Math.trunc(seconds / 60), 'minute'] : Math.abs(seconds) < 86400 ? [Math.trunc(seconds / 3600), 'hour'] : [Math.trunc(seconds / 86400), 'day'];
    return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(amount, unit);
  }
}
