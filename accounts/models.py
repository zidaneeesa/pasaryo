from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


# Custom manager untuk User, menggunakan email sebagai identifier utama
class UserManager(BaseUserManager):

    # Membuat user biasa dengan email dan password
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email wajib diisi")

        user = self.model(
            email=self.normalize_email(email),
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    # Membuat superuser dengan role admin, is_staff, dan is_superuser
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields["is_staff"] is not True:
            raise ValueError("Superuser harus memiliki is_staff=True")

        if extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser harus memiliki is_superuser=True")

        if extra_fields["role"] != User.Role.ADMIN:
            raise ValueError("Superuser harus memiliki role admin")

        return self.create_user(email, password, **extra_fields)


# Model user custom, login pakai email, mendukung role ADMIN dan USER
class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        USER = "user", "User"

    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.USER,
    )
    date_of_birth = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email
    

# Alamat pengiriman user, satu user bisa punya banyak alamat tapi hanya 1 alamat utama
class UserAddress(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    label = models.CharField(max_length=50)
    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=20)
    street_address = models.TextField()
    subdistrict = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)
    is_main = models.BooleanField(default=False)

    class Meta:
        db_table = "user_addresses"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_main=True),
                name="unique_main_address_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.label} - {self.recipient_name}"