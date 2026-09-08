CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE sales (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    product_name TEXT NOT NULL,
    stock_count INT NOT NULL,
    price_cents INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR NOT NULL,
    sale_id UUID NOT NULL REFERENCES sales(id),
    buyer_email TEXT NOT NULL,
    reservation_id VARCHAR NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE sales ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_sales ON sales
    USING (tenant_id = current_setting('app.current_tenant'));

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_orders ON orders
    USING (tenant_id = current_setting('app.current_tenant'));