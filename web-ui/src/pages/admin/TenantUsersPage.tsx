import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiFetch } from "@/auth/apiClient";
import { useAuth } from "@/auth/AuthProvider";

type TenantUser = { user_id: string; username: string; email: string; role: string };

export function TenantUsersPage() {
  const { t } = useTranslation('common');
  const { slug = "" } = useParams();
  const { me } = useAuth();
  const [users, setUsers] = useState<TenantUser[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "member">("member");
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    const r = await apiFetch(`/api/admin/tenants/${slug}/users`);
    if (r.ok) setUsers(await r.json());
    else setErr(await r.text());
  }
  useEffect(() => {
    load();
  }, [slug]);

  const canAdmin = me?.is_platform_admin || (me?.active_tenant === slug && me?.active_role === "admin");
  if (!canAdmin) return <div className="p-4">{t('admin.users.accessRequired')}</div>;

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    const r = await apiFetch(`/api/admin/tenants/${slug}/invites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
    });
    if (!r.ok) {
      setErr(await r.text());
      return;
    }
    setInviteEmail("");
    load();
  }

  async function changeRole(user_id: string, role: "admin" | "member") {
    const r = await apiFetch(`/api/admin/tenants/${slug}/users/${user_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!r.ok) setErr(await r.text());
    load();
  }

  async function remove(user_id: string) {
    if (!confirm(t('admin.users.removeConfirm'))) return;
    const r = await apiFetch(`/api/admin/tenants/${slug}/users/${user_id}`, { method: "DELETE" });
    if (!r.ok) setErr(await r.text());
    load();
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold mb-4">{slug} — {t('admin.users.title')}</h1>
      <form onSubmit={invite} className="flex gap-2 mb-4">
        <input
          className="border rounded px-2 py-1 flex-1"
          placeholder={t('admin.users.emailPlaceholder')}
          value={inviteEmail}
          onChange={(e) => setInviteEmail(e.target.value)}
        />
        <select
          className="border rounded px-2 py-1"
          value={inviteRole}
          onChange={(e) => setInviteRole(e.target.value as "admin" | "member")}
        >
          <option value="member">{t('admin.users.roleMember')}</option>
          <option value="admin">{t('admin.users.roleAdmin')}</option>
        </select>
        <button type="submit" className="border rounded px-3 py-1">
          {t('admin.users.inviteButton')}
        </button>
      </form>
      {err && <div className="text-red-600 mb-3">{err}</div>}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th>{t('admin.users.colUser')}</th>
            <th>{t('admin.users.colEmail')}</th>
            <th>{t('admin.users.colRole')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.user_id} className="border-b">
              <td>{u.username}</td>
              <td>{u.email}</td>
              <td>
                <select
                  value={u.role}
                  onChange={(e) => changeRole(u.user_id, e.target.value as "admin" | "member")}
                >
                  <option value="member">{t('admin.users.roleMember')}</option>
                  <option value="admin">{t('admin.users.roleAdmin')}</option>
                </select>
              </td>
              <td className="text-right">
                <button onClick={() => remove(u.user_id)} className="text-red-600">
                  {t('admin.users.removeButton')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
