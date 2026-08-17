package com.bookhaven.android.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.bookhaven.android.data.db.entity.CachedBook

@Dao
interface CachedBookDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(books: List<CachedBook>)

    @Query("DELETE FROM cached_books")
    suspend fun clear()

    @Query("SELECT * FROM cached_books ORDER BY title COLLATE NOCASE ASC")
    suspend fun getAll(): List<CachedBook>
}
