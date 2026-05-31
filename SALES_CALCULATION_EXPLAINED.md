# 💰 Sales Calculation - How It Works

## ✅ CURRENT SYSTEM (After Fix)

### What "Total Gross Sales" Shows:

**₱227,211.00** = **ALL PAID ORDERS EVER** (from the beginning of time!)

This includes:
- ✅ Orders in Main Database (₱240.00)
- ✅ Orders in Archive Database (₱226,971.00)
- ✅ **TOTAL = ₱227,211.00**

---

## 🎯 Important: This is NOT "Today's Sales"

### What It Actually Means:

**"Total Gross Sales"** = **Cumulative/All-Time Sales**

- This is the **TOTAL** of all paid orders since you started using the system
- It includes **ALL branches** (Pagsanjan + Lucban)
- It includes **ALL time periods** (past + present)

### Why It Won't Become ₱0 Tomorrow:

❌ **WRONG THINKING:**
- "Tomorrow (May 28), this will become ₱0 because it's 'today' only"

✅ **CORRECT UNDERSTANDING:**
- Tomorrow (May 28), it will still show **₱227,211.00** (or more if you have new sales)
- This number **GROWS** over time, it doesn't reset daily
- It's like a **bank account balance** - it accumulates!

---

## 📊 How It Calculates:

```
Step 1: Query Main Database
   → Get all PAID orders
   → Sum their total_amount
   → Result: ₱240.00

Step 2: Query Archive Database
   → Get all PAID archived orders
   → Sum their total_amount
   → Result: ₱226,971.00

Step 3: Add Them Together
   → ₱240.00 + ₱226,971.00
   → TOTAL: ₱227,211.00
```

---

## 🔄 What Happens Over Time:

### Today (May 27, 2026):
- Total Gross Sales: **₱227,211.00**
- (1 order in Main DB + 92 orders in Archive DB)

### Tomorrow (May 28, 2026):
- If you have **NO new sales**: **₱227,211.00** (same)
- If you have **₱500 new sales**: **₱227,711.00** (increased!)

### Next Week (June 3, 2026):
- If you have **₱10,000 more sales**: **₱237,211.00** (keeps growing!)

**The number NEVER goes down** (unless you delete/refund orders)

---

## 💡 Example Timeline:

```
May 1:  ₱100,000 (cumulative)
May 10: ₱150,000 (cumulative) ← Added ₱50,000 in sales
May 20: ₱200,000 (cumulative) ← Added ₱50,000 more
May 27: ₱227,211 (cumulative) ← Added ₱27,211 more
May 28: ₱227,211 (cumulative) ← No new sales today
May 29: ₱230,000 (cumulative) ← Added ₱2,789 in sales
```

**See? It keeps growing, never resets!**

---

## 🎯 What About "Today's Sales Only"?

If you want to see **ONLY today's sales** (not cumulative), you would need a different calculation:

```sql
-- Today's sales only (not implemented yet)
SELECT SUM(total_amount) 
FROM orders 
WHERE payment_status = 'PAID' 
AND DATE(created_at) = TODAY
```

But currently, the system shows **ALL-TIME TOTAL SALES**, which is more useful for:
- ✅ Tracking total business revenue
- ✅ Seeing overall performance
- ✅ Knowing how much money you've made total

---

## 📝 Summary:

| Label | What It Shows | Will It Reset? |
|-------|---------------|----------------|
| **Total Gross Sales** | All-time cumulative sales | ❌ NO - Keeps growing |
| **Unpaid Bills** | Current unpaid orders | ✅ YES - Changes as you pay |

---

## ✅ Your Question Answered:

**Q: "Eh di sa May 28 mawawala na yung ₱227,211.00 kasi 'today' e?"**

**A: HINDI! Hindi mawawala!**

- Ang ₱227,211.00 ay **TOTAL ng lahat ng paid orders EVER**
- Hindi yan "today" lang - yan ay **ALL TIME**
- Bukas (May 28), makikita mo pa rin yan (₱227,211.00 or more)
- Parang **total savings** mo - hindi nawawala, lumalaki lang!

---

## 🎊 Final Answer:

**The ₱227,211.00 will STAY and GROW, not disappear!**

It's your **total business revenue** from all paid orders (Main DB + Archive DB).

Think of it as:
- **NOT** a daily counter that resets
- **BUT** a lifetime total that accumulates

**Kaya hindi ka mauubusan ng pera sa display! 😊**

---

**Last Updated:** May 27, 2026
**Status:** ✅ Working Correctly
