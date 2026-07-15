import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../../auth/apiClient";
import { useAuth } from "../../auth/AuthProvider";

type Tenant = { id: string; slug: string; name: string };

export function TenantsPage() {
  const { t } = useTranslation('common');
  const { me } = useAuth();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    const r = await apiFetch("/api/admin/tenants");
    if (r.ok) setTenants(await r.json());
  }
  useEffect(() => {
    load();
  }, []);

  if (!me?.is_platform_admin) {
    return <div className="p-4">{t('admin.tenants.accessRequired')}</div>;
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const r = await apiFetch("/api/admin/tenants", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, name }),
    });
    if (!r.ok) {
      setErr(await r.text());
      return;
    }
    setSlug("");
    setName("");
    load();
  }

  async function remove(s: string) {
    if (!confirm(t('admin.tenants.deleteConfirm', { slug: s }))) return;
    const r = await apiFetch(`/api/admin/tenants/${s}`, { method: "DELETE" });
    if (!r.ok) setErr(await r.text());
    load();
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold mb-4">{t('admin.tenants.title')}</h1>
      <form onSubmit={create} className="flex gap-2 mb-4">
        <input
          className="border rounded px-2 py-1"
          placeholder={t('admin.tenants.slugPlaceholder')}
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
        />
        <input
          className="border rounded px-2 py-1 flex-1"
          placeholder={t('admin.tenants.namePlaceholder')}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" className="border rounded px-3 py-1">
          {t('admin.tenants.createButton')}
        </button>
      </form>
      {err && <div className="text-red-600 mb-3">{err}</div>}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th>{t('admin.tenants.colSlug')}</th>
            <th>{t('admin.tenants.colName')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {tenants.map((tenant) => (
            <tr key={tenant.id} className="border-b">
              <td>{tenant.slug}</td>
              <td>{tenant.name}</td>
              <td className="text-right">
                <button onClick={() => remove(tenant.slug)} className="text-red-600">
                  {t('admin.tenants.deleteButton')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
