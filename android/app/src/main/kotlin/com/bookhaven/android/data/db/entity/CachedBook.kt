package com.bookhaven.android.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

/** Minimal offline snapshot of the library grid, refreshed after each successful online load. */
@Entity(tableName = "cached_books")
data class CachedBook(
    @PrimaryKey val id: Int,
    val title: String,
    val author: String,
    val format: String,
    val category: String
)
