create table if not exists analyses (
    id text primary key,
    created_at timestamptz not null,
    image_path text not null,
    status text not null,
    payload jsonb not null
);
