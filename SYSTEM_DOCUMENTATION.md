# System Documentation: Le Maison - Yelo Lane

This document contains the core system specifications, including the Test Plan, Input-Process-Output (IPO) model, and the System Flowchart.

---

## 1. Admin Page Test Plan

| Case No. | Test Plan | Description |
| :--- | :--- | :--- |
| 1.0 | Login | Ensure admins can log in with valid credentials and are denied access with invalid ones. Verify secure handling of failed attempts and availability of password recovery. |
| 2.0 | Forget Password | To authenticate whether administrators can recover their accounts via OTP verification in the event of forgetting their password. |
| 3.0 | Dashboard (Overview) | Confirm the dashboard loads properly, displays real-time data in widgets like Total Sales, Active Orders, Pending Reservations, and Recent System Activity. |
| 4.0 | Orders Management | Check access to the orders module. Verify the functionality of order listings, search/filter options, viewing detailed receipts, and updating processing statuses. |
| 5.0 | Walk-in Order (POS) | Validate that the Walk-in Order module functions correctly as a point of sale, allowing staff to select items, calculate totals, and process payments on-site. |
| 6.0 | Kitchen Display | Verify the Kitchen module shows incoming orders clearly, allowing kitchen staff to reliably mark items as "preparing" or "ready" in real-time. |
| 7.0 | Deliveries Tracking | Confirm the deliveries module loads correctly. Ensure the Admin can monitor assigned riders on the map and view live delivery status updates. |
| 8.0 | Reservations | Validate that the Admin can view, approve, reject, or modify customer table reservations and that status changes trigger proper user notifications. |
| 9.0 | Menu Management | Verify the Admin can add, edit, or remove food items and categories, and ensure that changes reflect instantly on the customer-facing web and mobile apps. |
| 10.0 | Inventory | Check access to the inventory module. Validate the ability to track ingredient stock levels, update quantities, and flag low-stock items. |
| 11.0 | User Approvals | Verify the Admin can manage registered accounts, approve or reject rider/staff access requests, and block or unblock user accounts. |
| 12.0 | Reviews | Check that the Admin can view and filter customer reviews and feedback securely from the system interface. |
| 13.0 | Analytics | Confirm that the analytics page accurately renders charts, sales reports, and historical data trends without loading errors. |
| 14.0 | Settings | Validate that global system settings (such as shop hours, contact details, or notification preferences) can be modified and saved properly. |

---

## 2. Cashier Page Test Plan

| Case No. | Test Plan | Description |
| :--- | :--- | :--- |
| **1.0** | **View Live Orders** | Monitor real-time status of all PENDING, PREPARING, and READY orders. |
| **2.0** | **Create Walk-in Orders** | Manually input and process orders for on-site customers. |
| **3.0** | **Process Payments** | Update payment status from UNPAID to PAID and select payment methods. |
| **4.0** | **Generate Receipts** | Produce and print itemized receipts for completed transactions. |
| **5.0** | **View Order History** | Access paginated records of all past transactions and sales data. |
| **6.0** | **Customer Messaging** | Access and respond to real-time customer inquiries via the chat portal. |

---

## 3. Kitchen Side Test Plan

| Case No. | Test Plan | Description |
| :--- | :--- | :--- |
| **1.0** | **Staff Log In** | Securely access the kitchen portal using staff credentials (KITCHEN/STAFF/ADMIN roles). |
| **2.0** | **Order Queue Dashboard** | View live incoming orders categorized by status: Pending, Preparing, and Ready for Pickup. |
| **3.0** | **Update Order Status** | Transition orders through preparation stages (e.g., from PENDING to PREPARING or READY). |
| **4.0** | **Ingredient Auto-Deduction** | Verify that moving an order to "Preparing" automatically deducts required ingredients from kitchen stock. |
| **5.0** | **Kitchen Pantry Management** | View and manually adjust current kitchen stock levels for all ingredients. |
| **6.0** | **Recipe Reference** | View itemized ingredient lists for all menu items to ensure preparation accuracy. |
| **7.0** | **Stock Requests** | Submit and monitor requests to the warehouse for ingredient replenishment. |
| **8.0** | **Real-time Notifications** | Receive instant socket alerts for new orders and status updates across the system. |
| **9.0** | **Logout** | Securely terminate the session and return to the kitchen login screen. |

---

## 4. Input-Process-Output (IPO) Model

| **INPUT** | **PROCESS** | **OUTPUT** |
| :--- | :--- | :--- |
| **User Data**<br>• Login Credentials<br>• Customer Profile<br>• Account Registration | **Authentication & Security**<br>• User login verification<br>• Account authorization<br>• Data Encryption | **Access Control**<br>• Authorized user access<br>• Encrypted user credentials |
| **Ordering & POS**<br>• Selected Menu Items<br>• Order Type<br>• Customer Details<br>• Payment Info | **Order Lifecycle Management**<br>• Real-time order calculation<br>• Stock level deduction<br>• Order queuing<br>• Payment processing | **Order fulfillment**<br>• Generated Digital Receipt<br>• Printed QR or Order IDs<br>• Transaction records |
| **Reservations**<br>• Date and Time<br>• Table Selection / Pax<br>• Downpayment details | **Reservation Handling**<br>• Availability checking<br>• Table assignment logic<br>• Booking approval/rejection | **Booking Confirmation**<br>• Status notification<br>• Daily reservation master list |
| **Kitchen Preparation**<br>• New incoming orders<br>• Preparation estimates | **Kitchen Queue Management**<br>• Real-time notifications<br>• Status categorization | **Production Feedback**<br>• Real-time update to Customer<br>• Served status for staff |
| **Deliveries (Riders)**<br>• GPS location<br>• Delivery proof<br>• Rider acceptance | **Logistics Tracking**<br>• Calculating delivery routes<br>• Map visualization<br>• Fee calculation | **Delivery Receipt**<br>• "Order Delivered" status<br>• Tracked rider location |
| **Inventory & Supply**<br>• Stocks to be added<br>• Critical stock alerts | **Inventory Tracking**<br>• Real-time stock deduction<br>• Monitoring expiration / cost | **Stock Reports**<br>• Low stock notifications<br>• Automated inventory logs |
| **Analytics & Feedback**<br>• Transaction logs<br>• Customer Reviews | **Data Compilation**<br>• Sales report generation<br>• Top-selling items calculation<br>• Sentiment analysis | **System Reports**<br>• Sales performance graphs<br>• Business insight reports |

---

## 5. System Flowchart

```mermaid
flowchart TD
    %% Roles Colors
    classDef customer fill:#f9f,stroke:#333,stroke-width:2px;
    classDef admin fill:#ccf,stroke:#333,stroke-width:2px;
    classDef kitchen fill:#cfc,stroke:#333,stroke-width:2px;
    classDef rider fill:#fdd,stroke:#333,stroke-width:2px;

    %% START (Customer Role)
    Start((START)) --> Auth[User Login / Registration]
    Auth --> Choice{Select Action}
    
    %% BRANCH 1: ORDERING
    Choice -- "Ordering Food" --> Order[Browse Menu & Place Order]
    Order --> Pay{Payment Required?}
    
    Pay -- "Yes" --> ProcessPay[Process via GCash/Online]
    Pay -- "No / COD" --> ProcessCOD[Mark pending COD]
    
    ProcessPay --> AdminCheck
    ProcessCOD --> AdminCheck

    %% ADMIN ROLE
    AdminCheck{Admin Approval?}
    AdminCheck -- "Rejected" --> Refund[Notify / Refund Order]
    Refund --> End((END))
    
    AdminCheck -- "Approved" --> InvCheck[Update Inventory Stocks]
    InvCheck --> KitchenQueue[Add to Kitchen Queue]

    %% KITCHEN ROLE
    KitchenQueue --> Prepping[Kitchen Preparation Stage]
    Prepping --> FoodReady{Is Food Ready?}
    
    FoodReady -- "Wait" --> Prepping
    FoodReady -- "Yes" --> ReadyNotif[Mark as READY & Notify Customer]

    %% BRANCH: PICKUP vs DELIVERY
    ReadyNotif --> OrderType{Order Type?}
    
    OrderType -- "Dine-In / Pickup" --> CustomerPickup[Customer Receives Order]
    CustomerPickup --> Complete((COMPLETED))

    OrderType -- "Delivery" --> RiderAssign[Notify Available Riders]

    %% RIDER ROLE
    RiderAssign --> RiderAccept{Rider Accepts?}
    RiderAccept -- "No" --> RiderAssign
    RiderAccept -- "Yes" --> RiderGPSTrack[Track Rider GPS Location]
    
    RiderGPSTrack --> Delivered[Rider Delivers to Customer]
    Delivered --> Complete((COMPLETED))

    %% BRANCH 2: RESERVATIONS
    Choice -- "Reservation" --> Reserve[Select Table & Date]
    Reserve --> ResAdmin{Admin Approval?}
    ResAdmin -- "Reject" --> End
    ResAdmin -- "Approve" --> ResNotify[Notify Customer of Approved Slot]
    ResNotify --> Complete

    %% Apply Classes
    class Start,End,Complete customer;
    class Auth,Order,Choice,Pay,ProcessPay,ProcessCOD customer;
    class AdminCheck,InvCheck,ResAdmin admin;
    class KitchenQueue,Prepping,FoodReady,ReadyNotif kitchen;
    class RiderAssign,RiderAccept,RiderGPSTrack,Delivered rider;
```
