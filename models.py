import uuid
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


# ============================================================
# Product — your existing table, kept exactly as you have it
# ============================================================
class Product(Base):
    __tablename__ = "products"

    id              = Column(Integer, primary_key=True, index=True)
    sku             = Column(String, unique=True, index=True)
    name            = Column(String)
    category        = Column(String)                          # cleanser, moisturizer, serum, ...
    price           = Column(Float)
    stock           = Column(Integer)
    skin_types      = Column(String)                          # "oily,dry,combination,sensitive"
    concerns        = Column(String)                          # "acne,dryness,aging"
    description     = Column(Text)
    ingredients     = Column(Text)
    brand           = Column(String)
    volume          = Column(String)
    image_filename  = Column(String)


# ============================================================
# Order — one row per confirmed order
# Customer info is collected AFTER the user confirms the order
# (name, phone, address are asked via chat before we insert)
# ============================================================
class Order(Base):
    __tablename__ = "orders"

    id             = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())[:8].upper())
    customer_name  = Column(String, nullable=False)
    phone          = Column(String, nullable=False)
    address        = Column(String, nullable=False)
    status         = Column(String, default="pending")       # pending → confirmed → shipped → delivered
    created_at     = Column(DateTime, server_default=func.now())

    # ── relationship: one Order has many OrderItems ──
    items = relationship("OrderItem", back_populates="order")


# ============================================================
# OrderItem — one row per product line in an order
# quantity lets the user have e.g. 2x of the same product
# ============================================================
class OrderItem(Base):
    __tablename__ = "order_items"

    id         = Column(Integer, primary_key=True, index=True)
    order_id   = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity   = Column(Integer, default=1)
    price      = Column(Float, nullable=False)                # snapshot price at time of order

    # ── relationships ──
    order   = relationship("Order", back_populates="items")
    product = relationship("Product")