import { useEffect, useState } from 'react';
import { Alert, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormControlLabel, FormGroup, InputLabel, MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { usersAPI } from '../../api/users';
import type { ManagedDepartment, ManagedRole, ManagedUser } from '../../api/users';

export function UserManagement() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [error, setError] = useState('');
  const [roles, setRoles] = useState<ManagedRole[]>([]);
  const [departments, setDepartments] = useState<ManagedDepartment[]>([]);
  const [open, setOpen] = useState(false);
  const [roleOpen, setRoleOpen] = useState(false);
  const [departmentOpen, setDepartmentOpen] = useState(false);
  const [departmentName, setDepartmentName] = useState('');
  const [form, setForm] = useState({ full_name: '', email: '', password: '', role_id: '', department_id: '' });
  const [roleForm, setRoleForm] = useState({ name: '', role_type: 'Officer' as 'Manager' | 'Officer', permissions: [] as string[] });
  const [savingRole, setSavingRole] = useState(false);
  const [roleMessage, setRoleMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const permissionOptions = [
    ['request:create', 'Submit report requests'],
    ['request:view_own', 'View own requests'],
    ['request:view_all', 'View all tickets'],
    ['request:view_assigned', 'View assigned tickets'],
    ['request:process', 'Process and update tickets'],
    ['request:assign', 'Assign tickets'],
    ['request:approve', 'Approve requests'],
    ['request:review', 'Review completed reports'],
    ['request:reject', 'Reject requests'],
    ['request:cancel', 'Cancel requests'],
    ['request:comment', 'Reply to ticket communications'],
    ['request:internal_note', 'Add internal MIS notes'],
    ['request:upload', 'Upload report files'],
    ['report:download', 'Download reports'],
    ['report:export', 'Export ticket data'],
    ['feedback:create', 'Submit service feedback'],
    ['user:manage', 'Manage users'],
    ['role:manage', 'Manage roles and permissions'],
  ];
  const getError = (error: unknown, fallback: string) => {
    if (typeof error === 'object' && error !== null && 'response' in error) {
      const response = (error as { response?: { data?: { detail?: string } } }).response;
      if (response?.data?.detail) return response.data.detail;
    }
    return fallback;
  };

  useEffect(() => {
    Promise.all([usersAPI.list(), usersAPI.roles(), usersAPI.departments()]).then(([userResponse, roleResponse, departmentResponse]) => { setUsers(userResponse.data); setRoles(roleResponse.data); setDepartments(departmentResponse.data); }).catch((err) => {
      setError(err.response?.data?.detail || 'Unable to load users');
    }).finally(() => setLoading(false));
  }, []);

  const saveUser = async () => { try { const response = await usersAPI.create({ ...form, role_id: form.role_id ? Number(form.role_id) : null, department_id: form.department_id ? Number(form.department_id) : null }); setUsers((current) => [...current, response.data]); setOpen(false); setForm({ full_name: '', email: '', password: '', role_id: '', department_id: '' }); } catch (err: unknown) { setError(getError(err, 'Unable to create user')); } };
  const toggleUser = async (user: ManagedUser) => { try { const response = await usersAPI.update(user.id, { is_active: !user.is_active }); setUsers((current) => current.map((item) => item.id === user.id ? response.data : item)); } catch (err: unknown) { setError(getError(err, 'Unable to update user')); } };
  const changeRole = async (user: ManagedUser, roleId: string) => { try { const response = await usersAPI.update(user.id, { role_id: roleId ? Number(roleId) : null }); setUsers((current) => current.map((item) => item.id === user.id ? response.data : item)); } catch (err: unknown) { setError(getError(err, 'Unable to assign role')); } };
  const saveRole = async () => {
    setSavingRole(true);
    setRoleMessage('');
    try {
      const response = await usersAPI.createRole({ name: roleForm.name.trim(), role_type: roleForm.role_type, permissions: roleForm.permissions });
      setRoles((current) => [...current, response.data]);
      setRoleForm({ name: '', role_type: 'Officer', permissions: [] });
      setRoleMessage('Role created successfully.');
    } catch (err: unknown) {
      setRoleMessage(getError(err, 'Unable to create role'));
    } finally {
      setSavingRole(false);
    }
  };
  const togglePermission = (permission: string) => setRoleForm((current) => ({ ...current, permissions: current.permissions.includes(permission) ? current.permissions.filter((item) => item !== permission) : [...current.permissions, permission] }));
  const saveDepartment = async () => { try { const response = await usersAPI.createDepartment({ name: departmentName.trim(), manager_id: null }); setDepartments((current) => [...current, response.data]); setDepartmentName(''); setDepartmentOpen(false); } catch (err: unknown) { setError(getError(err, 'Unable to create department')); } };

  return (
    <Stack spacing={2}>
      <div>
        <Typography variant="h4">User management</Typography>
        <Typography color="text.secondary">Create accounts, assign operational roles, and control access.</Typography>
        <Stack direction="row" spacing={1} sx={{ mt: 2 }}><Button variant="contained" onClick={() => setOpen(true)}>Create user</Button><Button variant="outlined" onClick={() => setRoleOpen(true)}>Create role</Button><Button variant="outlined" onClick={() => setDepartmentOpen(true)}>Create department</Button></Stack>
      </div>
      {error && <Alert severity="error">{error}</Alert>}
      {loading && <Alert severity="info">Loading user management...</Alert>}
      <Paper sx={{ overflowX: 'auto' }}>
        <Table aria-label="User management table">
          <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Email</TableCell><TableCell>Department</TableCell><TableCell>Role</TableCell><TableCell>Status</TableCell><TableCell>Actions</TableCell></TableRow></TableHead>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id} hover>
                <TableCell>{user.full_name || 'Unnamed user'}</TableCell>
                <TableCell>{user.email}</TableCell>
                <TableCell>{departments.find((department) => department.id === user.department_id)?.name || 'Unassigned'}</TableCell><TableCell>{user.is_superuser ? 'System Administrator' : <Select size="small" value={user.role_id || ''} onChange={(event) => changeRole(user, String(event.target.value))} sx={{ minWidth: 150 }}><MenuItem value="">Requester</MenuItem>{roles.map((role) => <MenuItem key={role.id} value={role.id}>{role.name}</MenuItem>)}</Select>}</TableCell>
                <TableCell><Chip size="small" label={user.is_active ? 'Active' : 'Inactive'} color={user.is_active ? 'success' : 'default'} /></TableCell>
                <TableCell><Button size="small" onClick={() => toggleUser(user)}>{user.is_active ? 'Deactivate' : 'Activate'}</Button></TableCell>
              </TableRow>
            ))}
            {!users.length && !error && <TableRow><TableCell colSpan={6}>No users found.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Paper>
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm"><DialogTitle>Create user</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField label="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /><TextField label="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /><TextField label="Initial password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /><FormControl><InputLabel>Department</InputLabel><Select label="Department" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: String(e.target.value) })}>{departments.map((department) => <MenuItem key={department.id} value={department.id}>{department.name}</MenuItem>)}</Select></FormControl><FormControl><InputLabel>Role</InputLabel><Select label="Role" value={form.role_id} onChange={(e) => setForm({ ...form, role_id: String(e.target.value) })}><MenuItem value="">Requester</MenuItem>{roles.map((role) => <MenuItem key={role.id} value={role.id}>{role.name}</MenuItem>)}</Select></FormControl></Stack></DialogContent><DialogActions><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="contained" onClick={saveUser} disabled={!form.full_name || !form.email || !form.password}>Create</Button></DialogActions></Dialog>
      <Dialog open={departmentOpen} onClose={() => setDepartmentOpen(false)} fullWidth maxWidth="sm"><DialogTitle>Create department</DialogTitle><DialogContent><TextField fullWidth autoFocus sx={{ mt: 1 }} label="Department name" placeholder="Finance, Digital, Retail..." value={departmentName} onChange={(e) => setDepartmentName(e.target.value)} /></DialogContent><DialogActions><Button onClick={() => setDepartmentOpen(false)}>Cancel</Button><Button variant="contained" onClick={saveDepartment} disabled={!departmentName.trim()}>Create department</Button></DialogActions></Dialog>
      <Dialog open={roleOpen} onClose={() => { setRoleOpen(false); setRoleMessage(''); }} fullWidth maxWidth="sm"><DialogTitle>Create role</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField label="Role name" value={roleForm.name} onChange={(e) => setRoleForm({ ...roleForm, name: e.target.value })} /><FormControl><InputLabel>Role type</InputLabel><Select label="Role type" value={roleForm.role_type} onChange={(e) => setRoleForm({ ...roleForm, role_type: e.target.value as 'Manager' | 'Officer' })}><MenuItem value="Officer">Officer</MenuItem><MenuItem value="Manager">Manager</MenuItem></Select></FormControl><Typography variant="subtitle2">Select permissions</Typography><FormGroup>{permissionOptions.map(([permission, label]) => <FormControlLabel key={permission} control={<Checkbox checked={roleForm.permissions.includes(permission)} onChange={() => togglePermission(permission)} />} label={label} />)}</FormGroup>{roleMessage && <Alert severity={roleMessage === 'Role created successfully.' ? 'success' : 'error'}>{roleMessage}</Alert>}</Stack></DialogContent><DialogActions><Button onClick={() => setRoleOpen(false)}>Cancel</Button><Button variant="contained" onClick={saveRole} disabled={savingRole || !roleForm.name.trim() || !roleForm.permissions.length}>{savingRole ? 'Creating...' : 'Create role'}</Button></DialogActions></Dialog>
    </Stack>
  );
}