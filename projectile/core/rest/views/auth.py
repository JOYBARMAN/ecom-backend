from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from drf_spectacular.utils import extend_schema

from rest_framework import status
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import generate_unique_otp

from core.choices import ResetStatus, ResetType
from core.models import PasswordReset
from core.rest.serializers.password_reset import UserPasswordResetSerializer
from core.rest.serializers.register import UserRegistrationSerializer

from otp.choices import OtpType
from otp.models import OTP

User = get_user_model()


@extend_schema(description="You can register here")
class UserRegistration(CreateAPIView):
    serializer_class = UserRegistrationSerializer


class UserPasswordReset(APIView):
    permission_classes = ()
    serializer_class = UserPasswordResetSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            phone_number = serializer.validated_data.get("phone_number", None)
            new_password = serializer.validated_data.get("new_password", None)
            confirm_password = serializer.validated_data.get("confirm_password", None)
            otp = serializer.validated_data.get("otp", None)



            try:
                # Check if a user with the provided phone number exists
                user = User().get_all_actives().get(phone_number=phone_number)
            except User.DoesNotExist:
                return Response(
                    {"detail": "Person with the provided phone number does not exist."},
                    status=status.HTTP_404_NOT_FOUND
                )

            if not otp:
                # Check if there is an existing OTP created in the last 5 minutes
                five_minutes_ago = datetime.now() - timedelta(minutes=5)
                existing_otp = OTP.objects.filter(
                    user_id=user.id,
                    type=OtpType.PASSWORD_RESET,
                    is_used=False,
                    created_at__gte=five_minutes_ago,
                ).exists()

                if existing_otp:
                    # User already has a valid OTP created in the last 5 minutes
                    return Response({
                        'detail': "You already have an OTP. Please wait for the message."
                    }, status=status.HTTP_400_BAD_REQUEST)

                else:
                    # Generate a new OTP and send it to the user's phone
                    otp = generate_unique_otp()
                    OTP.objects.create(
                        user_id=user.id,
                        otp=otp,
                        type=OtpType.PASSWORD_RESET
                    )

                    # sending sms
                    # message = f"Your otp is {otp}."
                    # send_sms(user.phone_number, message)

                    # Return a response indicating that OTP will be sent to the user's phone
                    return Response({
                        "detail": "OTP has sent to your phone number.",
                        "code": "OTP"
                    }, status=status.HTTP_200_OK)

            else:
                if new_password and confirm_password:
                    if new_password != confirm_password:
                        return Response({
                            "detail": "new password and confirm password not matched"
                        }, status=status.HTTP_400_BAD_REQUEST)

                    try:
                        # Verify the OTP provided by the user
                        otp_record = OTP.objects.get(
                            user_id=user.id,
                            otp=otp,
                            is_used=False,
                            type=OtpType.PASSWORD_RESET
                        )
                    except OTP.DoesNotExist:
                        return Response({
                            "detail": "Invalid OTP."
                        }, status=status.HTTP_400_BAD_REQUEST)

                    if timezone.now() < (otp_record.created_at + timedelta(minutes=5)):
                        # Update the user's password
                        user.password = make_password(new_password)
                        user.save(update_fields=['password'])

                        # Mark the OTP as used
                        otp_record.is_used = True
                        otp_record.save(update_fields=['is_used'])

                        PasswordReset.objects.create(
                            user_id=user.id,
                            phone=user.phone_number,
                            reset_status=ResetStatus.SUCCESS,
                            otp_id=otp_record.id,
                            type=ResetType.SELF
                        )

                        return Response({
                            "detail": "Password reset successfully done"
                        }, status=status.HTTP_200_OK)

                    else:
                        return Response({
                            "detail": "OTP has expired."
                        }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({
                        "detail": "Please provide new password and confirm password"
                    }, status=status.HTTP_400_BAD_REQUEST)
