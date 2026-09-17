export function tagStyle(color: string) {
  const rgb = color.slice(1).match(/.{2}/g)?.map(value => Number.parseInt(value, 16) / 255) ?? [0, 0, 0];
  const luminance = rgb.map(value => value <= .03928 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((total, value, index) => total + value * [.2126, .7152, .0722][index], 0);
  return { backgroundColor: color, borderColor: color, color: luminance > .179 ? '#292722' : '#fffdfa' };
}
