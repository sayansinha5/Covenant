import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Alert } from '../components/ui/Alert';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { TextInput } from '../components/ui/Field';
import { api, problemOf } from '../lib/api';
import { saveCatalogBrief } from '../lib/catalog';
import { formatMoney } from '../lib/format';

const MAX_PICKS = 5;

function priceLabel(amount, currency) {
  if (!amount) return 'Price unknown';
  try {
    return `from ${formatMoney(amount, currency || 'USD')}`;
  } catch {
    return `from ${amount} ${currency || ''}`.trim();
  }
}

export function Catalog() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [products, setProducts] = useState(null);
  const [picked, setPicked] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function search(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const { data } = await api.post('/catalog/search', { query: query.trim() });
      setProducts(data.products);
      setPicked([]);
    } catch (failure) {
      setProducts(null);
      setError(problemOf(failure).detail);
    } finally {
      setBusy(false);
    }
  }

  function toggle(product) {
    setPicked((current) => {
      const exists = current.some((item) => item.id === product.id);
      if (exists) return current.filter((item) => item.id !== product.id);
      if (current.length >= MAX_PICKS) return current;
      return [...current, product];
    });
  }

  function brief() {
    saveCatalogBrief(picked);
    navigate('/assistant?from=catalog');
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-2xl text-sm text-ink-muted">
        Ground a listing job in products that are actually for sale. The prices and brands you pick
        become the brief, and the worker is paid only if the delivery keeps them.
      </p>
      <form onSubmit={search} className="flex flex-wrap items-center gap-2">
        <TextInput
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="silk kantha stole under $80"
          aria-label="Search the product catalog"
          className="max-w-md"
          required
          minLength={2}
        />
        <Button type="submit" loading={busy} loadingText="Searching…">
          Search catalog
        </Button>
      </form>
      {error && <Alert tone="danger">{error}</Alert>}
      {products?.length === 0 && (
        <Card className="p-6 text-ink-muted">No products matched that search.</Card>
      )}
      {products?.length > 0 && (
        <>
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-ink-muted">
              {picked.length} of {MAX_PICKS} selected
            </p>
            <Button onClick={brief} disabled={picked.length === 0}>
              Brief the assistant
            </Button>
          </div>
          <ul className="grid gap-3 md:grid-cols-2">
            {products.map((product) => {
              const selected = picked.some((item) => item.id === product.id);
              return (
                <li key={product.id}>
                  <Card className="flex h-full gap-3 p-3">
                    {product.image_url ? (
                      <img
                        src={product.image_url}
                        alt=""
                        className="size-20 shrink-0 rounded-md bg-wash object-cover"
                      />
                    ) : (
                      <span className="grid size-20 shrink-0 place-items-center rounded-md bg-wash text-xs text-ink-muted">
                        No image
                      </span>
                    )}
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <label className="flex items-start gap-2">
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={selected}
                          onChange={() => toggle(product)}
                        />
                        <span>
                          <span className="font-medium">{product.title}</span>
                          {product.brand && (
                            <span className="mt-0.5 block text-sm text-ink-muted">
                              {product.brand}
                            </span>
                          )}
                        </span>
                      </label>
                      <p className="text-sm font-medium tabular-nums">
                        {priceLabel(product.price_from, product.currency)}
                      </p>
                      <ul className="text-xs text-ink-muted">
                        {product.offers.map((offer) => (
                          <li key={`${product.id}-${offer.domain}`}>
                            {offer.url ? (
                              <a
                                href={offer.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-brand"
                              >
                                {offer.domain}
                              </a>
                            ) : (
                              offer.domain
                            )}
                            {offer.price ? ` · ${offer.currency} ${offer.price}` : ''}
                            {offer.commission_percent
                              ? ` · ${offer.commission_percent}% commission`
                              : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </Card>
                </li>
              );
            })}
          </ul>
        </>
      )}
      <p className="text-xs text-ink-muted">
        Product graph · Channel3. A buy link can earn commission; the price is what the listing must
        keep.
      </p>
    </div>
  );
}
