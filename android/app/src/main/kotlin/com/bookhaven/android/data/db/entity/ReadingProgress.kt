package com.bookhaven.android.data.db.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "reading_progress")
data class ReadingProgress(
    @PrimaryKey val bookId: Int,
    val position: String,       // CFI for EPUB; page index string for PDF/CBZ
    val progress: Float = 0f,   // 0–100 percentage
    val updatedAt: Long,
    // Column name must be snake_case to match the v3→v4 migration and getPending() query.
    @ColumnInfo(name = "pending_sync") val pendingSync: Boolean = false
)
