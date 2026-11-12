/** The brief the assistant sends on, so a listing job is tied to real offers. */

export const CATALOG_BRIEF_KEY = 'covenant.catalog-brief';

export function catalogBrief(products) {
  const lines = products.map((product, index) => {
    const brand = product.brand || 'brand unknown';
    const price = product.price_from
      ? `from ${product.currency} ${product.price_from}`
      : 'price unknown';
    const offers = (product.offers ?? [])
      .slice(0, 3)
      .map((offer) => {
        const amount = offer.price ? `${offer.currency} ${offer.price}` : 'price unknown';
        const commission = offer.commission_percent
          ? `, ${offer.commission_percent}% commission`
          : '';
        return `${offer.domain} ${amount}${commission}`;
      })
      .join('; ');
    return `${index + 1}. ${product.title} (${brand}, id ${product.id}) — ${price}. Offers: ${offers || 'none'}.`;
  });
  return [
    'Write catalogue listings for these real products. Do not change the brand, the title, or any price. The cheapest in-stock offer is the price the listing must show.',
    '',
    ...lines,
    '',
    'Hold the budget in escrow and pay only if every item matches.',
  ].join('\n');
}

export function saveCatalogBrief(products) {
  sessionStorage.setItem(CATALOG_BRIEF_KEY, catalogBrief(products));
}

export function readCatalogBrief() {
  try {
    return sessionStorage.getItem(CATALOG_BRIEF_KEY) ?? '';
  } catch {
    return '';
  }
}
