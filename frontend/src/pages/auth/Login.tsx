import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Container, Paper, Stack, TextField, Typography } from '@mui/material';
import { authAPI } from '../../api/auth';

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const response = await authAPI.login({ email, password });
      localStorage.setItem('access_token', response.data.access_token);
      await authAPI.me().then(({ data }) => localStorage.setItem('user_permissions', JSON.stringify(data.permissions)));
      navigate('/');
    } catch (err: unknown) {
      const detail = typeof err === 'object' && err !== null && 'response' in err ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail : undefined;
      setError(Array.isArray(detail) ? detail.map((item) => typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : String(item)).join(', ') : typeof detail === 'string' ? detail : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', background: 'linear-gradient(135deg, #f7f3f0 0%, #eee4e0 100%)' }}>
      <Container maxWidth="sm">
        <Paper elevation={0} sx={{ maxWidth: 440, mx: 'auto', p: { xs: 3, sm: 5 }, border: '1px solid #e3d5d5', borderRadius: 1 }}>
          <Stack spacing={3}>
            <Box><Typography sx={{ color: '#7B1235', fontSize: 12, fontWeight: 800, letterSpacing: 1.5 }}>AHADU BANK</Typography><Typography variant="h5" sx={{ mt: 1, fontWeight: 700 }}>MIS Service Desk</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>Sign in to manage report requests and communications.</Typography></Box>
            <form onSubmit={handleSubmit}>
              <Stack spacing={2}>
          <TextField
            fullWidth
            label="Email"
            margin="normal"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <TextField
            fullWidth
            label="Password"
            type="password"
            margin="normal"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
                {error && <Alert severity="error">{error}</Alert>}
                <Button type="submit" fullWidth variant="contained" disabled={submitting} sx={{ py: 1.25, bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}>{submitting ? 'Signing in...' : 'Sign in'}</Button>
                <Button fullWidth variant="text" onClick={() => navigate('/register')}>Create requester account</Button>
              </Stack>
            </form>
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
}
