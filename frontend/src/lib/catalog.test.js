import { describe, expect, it } from 'vitest';

import { catalogBrief } from './catalog';

describe('catalogBrief', () => {
  it('pins brand, id and the cheapest offer so the contract can check them', () => {
    const text = catalogBrief([
      {
        id: 'sku-1',
        title: 'Kantha stole',
        brand: 'Kantha & Co',
        currency: 'USD',
        price_from: '48.00',
        offers: [
          { domain: 'shop.example', price: '48.00', currency: 'USD', commission_percent: '5' },
        ],
      },
    ]);
    expect(text).toContain('Do not change the brand');
    expect(text).toContain('Kantha stole (Kantha & Co, id sku-1)');
    expect(text).toContain('from USD 48.00');
    expect(text).toContain('shop.example USD 48.00, 5% commission');
  });
});
