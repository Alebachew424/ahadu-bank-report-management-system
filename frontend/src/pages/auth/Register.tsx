import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Container, Paper, Stack, TextField, Typography } from '@mui/material';
import { authAPI } from '../../api/auth';

export function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await authAPI.register({ email, password, full_name: fullName });
      setSuccess(true);
      setTimeout(() => navigate('/login'), 1500);
    } catch (err: unknown) {
      const detail = typeof err === 'object' && err !== null && 'response' in err ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail : undefined;
      setError(Array.isArray(detail) ? detail.map((item) => typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : String(item)).join(', ') : typeof detail === 'string' ? detail : 'Registration failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', background: 'linear-gradient(135deg, #f7f3f0 0%, #eee4e0 100%)' }}>
      <Container maxWidth="sm">
        <Paper elevation={0} sx={{ maxWidth: 440, mx: 'auto', p: { xs: 3, sm: 5 }, border: '1px solid #e3d5d5', borderRadius: 1 }}>
          <Stack spacing={3}>
            <Box><Typography sx={{ color: '#7B1235', fontSize: 12, fontWeight: 800, letterSpacing: 1.5 }}>AHADU BANK</Typography><Typography variant="h5" sx={{ mt: 1, fontWeight: 700 }}>Requester registration</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>Create a business account for submitting report tickets.</Typography></Box>
        {success ? (
          <Typography color="success.main">Registration successful! Redirecting...</Typography>
        ) : (
          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Full Name"
              margin="normal"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
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
            <Button type="submit" fullWidth variant="contained" disabled={submitting} sx={{ py: 1.25, bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}>{submitting ? 'Creating account...' : 'Create account'}</Button>
            <Button fullWidth variant="text" onClick={() => navigate('/login')}>Back to sign in</Button>
          </form>
        )}
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
}
