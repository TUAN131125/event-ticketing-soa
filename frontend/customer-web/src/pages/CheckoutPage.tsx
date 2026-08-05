import { useSearchParams, useNavigate } from 'react-router-dom';
import { CreditCard, LockKeyhole } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Card, FormField, Input, Select } from '@event-ticketing/shared-ui';
import { useCreateBooking, useEvent } from '../app/hooks';
import { QueryState } from './PageState';
const schema = z.object({
  paymentMethod: z.enum(['CARD', 'BANK_TRANSFER', 'PAY_AT_VENUE']),
  cardholder: z.string().min(2, 'Enter the cardholder name').optional(),
  cardNumber: z.string().optional(),
});
type Values = z.infer<typeof schema>;
export function CheckoutPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const reservationId = params.get('reservationId') ?? '';
  const eventId = params.get('eventId') ?? '';
  const event = useEvent(eventId);
  const mutation = useCreateBooking();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { paymentMethod: 'CARD' },
  });
  const paymentMethod = form.watch('paymentMethod');
  if (!reservationId || !eventId)
    return (
      <QueryState
        error={new Error('Missing reservation')}
        retry={() => navigate('/events')}
        notFound
      />
    );
  if (event.isLoading)
    return (
      <section className="container page-section">
        <Card>
          <p>Loading your reservation…</p>
        </Card>
      </section>
    );
  if (event.isError || !event.data)
    return <QueryState error={event.error} retry={() => void event.refetch()} />;
  return (
    <section className="container page-section narrow-page">
      <div className="page-heading">
        <p className="eyebrow">Step 2 of 2</p>
        <h1>Complete your booking</h1>
        <p className="lede">Your seats are held while you complete this step.</p>
      </div>
      <Card>
        <form
          className="stack-form"
          onSubmit={form.handleSubmit((values) =>
            mutation.mutate(
              {
                eventId,
                reservationId,
                paymentMethod: values.paymentMethod,
                idempotencyKey: crypto.randomUUID(),
              },
              {
                onSuccess: (booking) =>
                  navigate(`/bookings/${encodeURIComponent(booking.bookingId)}?created=1`),
              },
            ),
          )}
        >
          <div className="checkout-summary">
            <strong>{event.data.name}</strong>
            <span>Reservation {reservationId}</span>
          </div>
          <FormField label="Payment method" error={form.formState.errors.paymentMethod?.message}>
            <Select {...form.register('paymentMethod')}>
              <option value="CARD">Card</option>
              <option value="BANK_TRANSFER">Bank transfer</option>
              <option value="PAY_AT_VENUE">Pay at venue</option>
            </Select>
          </FormField>
          {paymentMethod === 'CARD' && (
            <>
              <FormField label="Cardholder name" error={form.formState.errors.cardholder?.message}>
                <Input
                  {...form.register('cardholder')}
                  placeholder="Name on card"
                  autoComplete="cc-name"
                />
              </FormField>
              <FormField
                label="Card number"
                hint="Use a payment provider in production; card details are never sent to this UI service."
              >
                <Input
                  {...form.register('cardNumber')}
                  placeholder="•••• •••• •••• ••••"
                  autoComplete="cc-number"
                  inputMode="numeric"
                />
              </FormField>
            </>
          )}
          <div className="secure-note">
            <LockKeyhole size={16} /> Payments are processed securely by the booking service.
          </div>
          <Button type="submit" fullWidth disabled={mutation.isPending}>
            {mutation.isPending ? (
              'Confirming booking…'
            ) : (
              <>
                <CreditCard size={17} /> Confirm booking
              </>
            )}
          </Button>
          {mutation.isError && (
            <p className="form-error">
              {mutation.error instanceof Error
                ? mutation.error.message
                : 'The booking service could not complete payment.'}
            </p>
          )}
        </form>
      </Card>
    </section>
  );
}
